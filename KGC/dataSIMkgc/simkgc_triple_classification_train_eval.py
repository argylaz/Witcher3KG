import os, json, time, random, argparse
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW
from torch.cuda.amp import autocast, GradScaler
from transformers import AutoTokenizer, AutoModel

def set_seed(seed: int):
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

def load_triples_jsonl(path):
    data = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line)
                if "head" in obj and "relation" in obj and "tail" in obj:
                    data.append({"h": obj["head"], "r": obj["relation"], "t": obj["tail"]})
        return pd.DataFrame(data)
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return pd.DataFrame(columns=["h", "r", "t"])

def load_maps(data_dir):
    ent = pd.read_csv(os.path.join(data_dir, "entity2textlong.tsv"), sep="\t", header=None, names=["uri","desc"])
    rel = pd.read_csv(os.path.join(data_dir, "relation2text.txt"), sep="\t", header=None, names=["uri","desc"])
    ent2desc = dict(zip(ent["uri"], ent["desc"]))
    rel2desc = dict(zip(rel["uri"], rel["desc"]))
    entities = open(os.path.join(data_dir, "entities.txt"), encoding="utf-8").read().splitlines()
    return ent2desc, rel2desc, entities

def build_query_text(h, r, ent2desc, rel2desc):
    return f"{ent2desc.get(h,h)} {rel2desc.get(r,r)}"
def build_entity_text(e, ent2desc):
    return ent2desc.get(e, e)

#Training
class TrainDataset(Dataset):
    def __init__(self, df):
        self.df = df.reset_index(drop=True)
    def __len__(self): return len(self.df)
    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        return row["h"], row["r"], row["t"]

def collate_train(batch, tokenizer, ent2desc, rel2desc, max_len):
    hs, rs, ts = zip(*batch)
    q_texts = [build_query_text(h, r, ent2desc, rel2desc) for h, r in zip(hs, rs)]
    t_texts = [build_entity_text(t, ent2desc) for t in ts]
    q_enc = tokenizer(q_texts, padding=True, truncation=True, max_length=max_len, return_tensors="pt")
    t_enc = tokenizer(t_texts, padding=True, truncation=True, max_length=max_len, return_tensors="pt")
    return q_enc, t_enc

#Evaluation Triple Classification
def make_labeled_samples(pos_df, all_true_set, entities, neg_per_pos=1, seed=42):
    rng = random.Random(seed)
    samples = []
    for _, row in pos_df.iterrows():
        h, r, t = row["h"], row["r"], row["t"]
        samples.append((h, r, t, 1)) #True
        for _ in range(neg_per_pos):
            if rng.random() < 0.5:
                tt = rng.choice(entities)
                while (h, r, tt) in all_true_set: tt = rng.choice(entities)
                samples.append((h, r, tt, 0)) #False Tail
            else:
                hh = rng.choice(entities)
                while (hh, r, t) in all_true_set: hh = rng.choice(entities)
                samples.append((hh, r, t, 0)) #False Head
    return samples

class BiEncoder(nn.Module):
    def __init__(self, model_name):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(model_name)
        hs = self.encoder.config.hidden_size
        self.proj = nn.Linear(hs, hs)
        self.dropout = nn.Dropout(0.1)

    def encode(self, enc):
        out = self.encoder(**enc)
        cls = out.last_hidden_state[:, 0]
        x = self.dropout(cls)
        x = self.proj(x)
        x = nn.functional.normalize(x, p=2, dim=-1)
        return x

@torch.inference_mode()
def eval_triple_classification(model, tokenizer, pos_df, all_true_set, entities, ent2desc, rel2desc,
                               device, eval_batch, max_len, neg_per_pos, seed, threshold):
    model.eval()
    samples = make_labeled_samples(pos_df, all_true_set, entities, neg_per_pos=neg_per_pos, seed=seed)
    labels = [s[3] for s in samples]
    scores = []

    for i in range(0, len(samples), eval_batch):
        batch = samples[i:i+eval_batch]
        hs, rs, ts, _ = zip(*batch)
        q_texts = [build_query_text(h, r, ent2desc, rel2desc) for h, r in zip(hs, rs)]
        t_texts = [build_entity_text(t, ent2desc) for t in ts]
        q_enc = tokenizer(q_texts, padding=True, truncation=True, max_length=max_len, return_tensors="pt")
        t_enc = tokenizer(t_texts, padding=True, truncation=True, max_length=max_len, return_tensors="pt")
        q_enc = {k: v.to(device) for k, v in q_enc.items()}
        t_enc = {k: v.to(device) for k, v in t_enc.items()}
        q_emb = model.encode(q_enc)
        t_emb = model.encode(t_enc)
        #Cosine
        cos = torch.sum(q_emb * t_emb, dim=-1)
        scores.append(cos.cpu())

    all_scores = torch.cat(scores, dim=0).numpy()
    #Metrics
    y_true = list(map(int, labels))
    y_pred = [1 if s >= threshold else 0 for s in all_scores]
    tp = sum((yt==1 and yp==1) for yt, yp in zip(y_true, y_pred))
    tn = sum((yt==0 and yp==0) for yt, yp in zip(y_true, y_pred))
    fp = sum((yt==0 and yp==1) for yt, yp in zip(y_true, y_pred))
    fn = sum((yt==1 and yp==0) for yt, yp in zip(y_true, y_pred))
    acc = (tp + tn) / max(1, (tp + tn + fp + fn))
    prec = tp / max(1, (tp + fp))
    rec  = tp / max(1, (tp + fn))
    f1 = 0.0 if (prec + rec) == 0 else (2 * prec * rec) / (prec + rec)
    return {
        "accuracy": acc, "precision": prec, "recall": rec, "f1": f1,
        "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "threshold": threshold,
        "num_pos": int(sum(y_true)),
        "num_neg": int(len(y_true) - sum(y_true))}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_dir", required=True)
    ap.add_argument("--run_name", required=True)
    ap.add_argument("--model_name", default="bert-base-uncased")
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--train_batch", type=int, default=32)
    ap.add_argument("--eval_batch", type=int, default=64)
    ap.add_argument("--max_len", type=int, default=256)
    ap.add_argument("--neg_per_pos", type=int, default=1)
    ap.add_argument("--temperature", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--eval_every", type=int, default=1)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--out_dir", default="results")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    use_amp = (device == "cuda")
    set_seed(args.seed)

    ent2desc, rel2desc, entities = load_maps(args.data_dir)
    train_df = load_triples_jsonl(os.path.join(args.data_dir, "train.jsonl"))
    dev_path = os.path.join(args.data_dir, "dev.jsonl")
    if not os.path.exists(dev_path): dev_path = os.path.join(args.data_dir, "valid.jsonl")
    dev_df = load_triples_jsonl(dev_path)
    test_df = load_triples_jsonl(os.path.join(args.data_dir, "test.jsonl"))
    
    all_true_set = set(map(tuple, pd.concat([train_df, dev_df, test_df])[["h","r","t"]].values.tolist()))
    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = BiEncoder(args.model_name).to(device)
    optim = AdamW(model.parameters(), lr=args.lr)
    scaler = GradScaler(enabled=use_amp)

    # Train Dataset
    train_ds = TrainDataset(train_df)
    loader = DataLoader(
        train_ds,
        batch_size=args.train_batch,
        shuffle=True,
        pin_memory=(device == "cuda"),
        collate_fn=lambda b: collate_train(b, tokenizer, ent2desc, rel2desc, args.max_len))

    best_dev_f1 = -1.0
    best_ckpt_dir = os.path.join("checkpoints_simkgc_cls", args.run_name, "best")
    os.makedirs(best_ckpt_dir, exist_ok=True)

    history = {"epochs": [], "dev": [], "test": None}

    for ep in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        for q_enc, t_enc in loader:
            q_enc = {k: v.to(device, non_blocking=True) for k, v in q_enc.items()}
            t_enc = {k: v.to(device, non_blocking=True) for k, v in t_enc.items()}
            optim.zero_grad(set_to_none=True)
            with autocast(enabled=use_amp):
                q = model.encode(q_enc)
                t = model.encode(t_enc)
                #Contrastive loss with negatives in the batch
                logits = (q @ t.t()) / args.temperature
                labels = torch.arange(logits.size(0), device=device)
                loss = nn.CrossEntropyLoss()(logits, labels)
            scaler.scale(loss).backward()
            scaler.step(optim)
            scaler.update()
            total_loss += float(loss.detach().cpu())

        avg_loss = total_loss / max(1, len(loader))
        print(f"[{args.run_name}] epoch {ep}/{args.epochs} loss={avg_loss:.4f}")
        history["epochs"].append({"epoch": ep, "train_loss": avg_loss})

        if args.eval_every > 0 and (ep % args.eval_every == 0):
            # EVALUATION as Triple Classification
            dev_metrics = eval_triple_classification(
                model, tokenizer, dev_df, all_true_set, entities, ent2desc, rel2desc,
                device=device, eval_batch=args.eval_batch, max_len=args.max_len,
                neg_per_pos=args.neg_per_pos, seed=args.seed + 1000 + ep, threshold=args.threshold)
            history["dev"].append({"epoch": ep, **dev_metrics})
            print(f"[{args.run_name}] DEV (Triple Cls) {dev_metrics}")

            if dev_metrics["f1"] > best_dev_f1:
                best_dev_f1 = dev_metrics["f1"]
                torch.save(model.state_dict(), os.path.join(best_ckpt_dir, "model.pt"))
                tokenizer.save_pretrained(best_ckpt_dir)

    #Load best model and evaluate on test
    best_model = BiEncoder(args.model_name).to(device)
    best_model.load_state_dict(torch.load(os.path.join(best_ckpt_dir, "model.pt"), map_location=device))
    best_tok = AutoTokenizer.from_pretrained(best_ckpt_dir)

    test_metrics = eval_triple_classification(
        best_model, best_tok, test_df, all_true_set, entities, ent2desc, rel2desc,
        device=device, eval_batch=args.eval_batch, max_len=args.max_len,
        neg_per_pos=args.neg_per_pos, seed=args.seed + 2000, threshold=args.threshold)
    history["test"] = test_metrics
    print(f"[{args.run_name}] TEST (Triple Cls) {test_metrics}")

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, f"{args.run_name}.json")
    payload = {
        "run_name": args.run_name,
        "task": "TRIPLE_CLASSIFICATION",
        "method": "SimKGC (Bi-Encoder Contrastive)",
        "params": {
            "epochs": args.epochs,
            "lr": args.lr,
            "train_batch": args.train_batch,
            "max_len": args.max_len,
            "neg_per_pos": args.neg_per_pos,
            "threshold": args.threshold
        },
        "best_dev_f1": best_dev_f1,
        "history": history,
        "timestamp_unix": int(time.time())
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("Saved:", out_path)
if __name__ == "__main__":
    main()