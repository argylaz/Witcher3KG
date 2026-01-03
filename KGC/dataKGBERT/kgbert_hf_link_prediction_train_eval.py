import os, json, time, random, argparse
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW
from torch.cuda.amp import autocast, GradScaler
from transformers import AutoTokenizer, AutoModelForSequenceClassification

def set_seed(seed: int):
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

def load_triples(path: str):
    return pd.read_csv(path, sep="\t", header=None, names=["h","r","t"]).dropna()

def read_maps(data_dir: str):
    ent_df = pd.read_csv(os.path.join(data_dir, "entity2textlong.tsv"), sep="\t", header=None, names=["uri","desc"])
    rel_df = pd.read_csv(os.path.join(data_dir, "relation2text.txt"), sep="\t", header=None, names=["uri","desc"])
    entities = open(os.path.join(data_dir, "entities.txt"), encoding="utf-8").read().splitlines()
    ent2desc = dict(zip(ent_df["uri"], ent_df["desc"]))
    rel2desc = dict(zip(rel_df["uri"], rel_df["desc"]))
    return ent2desc, rel2desc, entities

def triple_to_text(h, r, t, ent2desc, rel2desc):
    hd = ent2desc.get(h, h)
    rd = rel2desc.get(r, r)
    td = ent2desc.get(t, t)
    return f"HEAD: {hd}\nRELATION: {rd}\nTAIL: {td}"

class TripleClsDataset(Dataset):
    def __init__(self, pos_df, all_true_set, entities, ent2desc, rel2desc, neg_per_pos=5):
        self.samples = []
        for _, row in pos_df.iterrows():
            h, r, t = row["h"], row["r"], row["t"]
            self.samples.append((triple_to_text(h, r, t, ent2desc, rel2desc), 1))

            for _ in range(neg_per_pos):
                if random.random() < 0.5:
                    tt = random.choice(entities)
                    while (h, r, tt) in all_true_set:
                        tt = random.choice(entities)
                    self.samples.append((triple_to_text(h, r, tt, ent2desc, rel2desc), 0))
                else:
                    hh = random.choice(entities)
                    while (hh, r, t) in all_true_set:
                        hh = random.choice(entities)
                    self.samples.append((triple_to_text(hh, r, t, ent2desc, rel2desc), 0))

    def __len__(self): 
        return len(self.samples)

    def __getitem__(self, idx): 
        return self.samples[idx]

def collate_fn(batch, tokenizer, max_len):
    texts, labels = zip(*batch)
    enc = tokenizer(list(texts), padding=True, truncation=True, max_length=max_len, return_tensors="pt")
    return enc, torch.tensor(labels, dtype=torch.long)

@torch.inference_mode()
def score_texts(model, tokenizer, texts, device, batch_size=64, max_len=256):
    model.eval()
    scores = []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i+batch_size]
        enc = tokenizer(chunk, padding=True, truncation=True, max_length=max_len, return_tensors="pt")
        enc = {k: v.to(device, non_blocking=True) for k, v in enc.items()}
        logits = model(**enc).logits
        prob_pos = torch.softmax(logits, dim=-1)[:, 1]
        scores.append(prob_pos.detach().cpu())
    return torch.cat(scores, dim=0).numpy()

def filtered_link_prediction_eval(model, tokenizer, df, all_true, entities, ent2desc, rel2desc, device, eval_batch, max_len):
    ranks = []
    for _, row in df.iterrows():
        h, r, t = row["h"], row["r"], row["t"]

        # tail
        cand_entities, cand_texts = [], []
        for e in entities:
            if e != t and (h, r, e) in all_true:
                continue
            cand_entities.append(e)
            cand_texts.append(triple_to_text(h, r, e, ent2desc, rel2desc))

        scores = score_texts(model, tokenizer, cand_texts, device, eval_batch, max_len)
        true_idx = cand_entities.index(t)
        true_score = scores[true_idx]
        ranks.append(1 + int((scores > true_score).sum()))

        # head
        cand_entities, cand_texts = [], []
        for e in entities:
            if e != h and (e, r, t) in all_true:
                continue
            cand_entities.append(e)
            cand_texts.append(triple_to_text(e, r, t, ent2desc, rel2desc))

        scores = score_texts(model, tokenizer, cand_texts, device, eval_batch, max_len)
        true_idx = cand_entities.index(h)
        true_score = scores[true_idx]
        ranks.append(1 + int((scores > true_score).sum()))

    rt = torch.tensor(ranks, dtype=torch.float)
    return {
        "MRR": torch.mean(1.0 / rt).item(),
        "MR": torch.mean(rt).item(),
        "Hits@1": torch.mean((rt <= 1).float()).item(),
        "Hits@3": torch.mean((rt <= 3).float()).item(),
        "Hits@10": torch.mean((rt <= 10).float()).item(),
        "num_queries": len(ranks)
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_dir", required=True)
    ap.add_argument("--run_name", required=True)
    ap.add_argument("--model_name", default="bert-base-uncased")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--train_batch", type=int, default=16)
    ap.add_argument("--eval_batch", type=int, default=64)
    ap.add_argument("--max_len", type=int, default=256)
    ap.add_argument("--neg_per_pos", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--eval_every", type=int, default=1)
    ap.add_argument("--out_dir", default="results")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    use_amp = (device == "cuda")
    set_seed(args.seed)

    ent2desc, rel2desc, entities = read_maps(args.data_dir)
    train_df = load_triples(os.path.join(args.data_dir, "train.tsv"))
    dev_df   = load_triples(os.path.join(args.data_dir, "dev.tsv"))
    test_df  = load_triples(os.path.join(args.data_dir, "test.tsv"))
    all_true = set(map(tuple, pd.concat([train_df, dev_df, test_df])[["h","r","t"]].values.tolist()))

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = AutoModelForSequenceClassification.from_pretrained(args.model_name, num_labels=2).to(device)

    train_ds = TripleClsDataset(train_df, all_true, entities, ent2desc, rel2desc, args.neg_per_pos)
    loader = DataLoader(
        train_ds,
        batch_size=args.train_batch,
        shuffle=True,
        pin_memory=(device == "cuda"),
        collate_fn=lambda b: collate_fn(b, tokenizer, args.max_len),
    )

    optim = AdamW(model.parameters(), lr=args.lr)
    scaler = GradScaler(enabled=use_amp)

    best_dev_mrr = -1.0
    best_ckpt_dir = os.path.join("checkpoints_kgbert", args.run_name, "best")
    os.makedirs(best_ckpt_dir, exist_ok=True)

    history = {"epochs": [], "dev": [], "test": None}

    for ep in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0

        for enc, labels in loader:
            enc = {k: v.to(device, non_blocking=True) for k, v in enc.items()}
            labels = labels.to(device, non_blocking=True)

            optim.zero_grad(set_to_none=True)
            with autocast(enabled=use_amp):
                out = model(**enc, labels=labels)
                loss = out.loss

            scaler.scale(loss).backward()
            scaler.step(optim)
            scaler.update()
            total_loss += float(loss.detach().cpu())

        avg_loss = total_loss / max(1, len(loader))
        print(f"[{args.run_name}] epoch {ep}/{args.epochs} loss={avg_loss:.4f}")
        history["epochs"].append({"epoch": ep, "train_loss": avg_loss})

        if args.eval_every > 0 and (ep % args.eval_every == 0):
            dev_metrics = filtered_link_prediction_eval(
                model, tokenizer, dev_df, all_true, entities, ent2desc, rel2desc,
                device=device, eval_batch=args.eval_batch, max_len=args.max_len
            )
            history["dev"].append({"epoch": ep, **dev_metrics})
            print(f"[{args.run_name}] DEV {dev_metrics}")

            if dev_metrics["MRR"] > best_dev_mrr:
                best_dev_mrr = dev_metrics["MRR"]
                model.save_pretrained(best_ckpt_dir)
                tokenizer.save_pretrained(best_ckpt_dir)

    # load best and eval on test
    best_model = AutoModelForSequenceClassification.from_pretrained(best_ckpt_dir).to(device)
    best_tok = AutoTokenizer.from_pretrained(best_ckpt_dir)

    test_metrics = filtered_link_prediction_eval(
        best_model, best_tok, test_df, all_true, entities, ent2desc, rel2desc,
        device=device, eval_batch=args.eval_batch, max_len=args.max_len
    )
    history["test"] = test_metrics
    print(f"[{args.run_name}] TEST {test_metrics}")

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, f"{args.run_name}.json")
    payload = {
        "run_name": args.run_name,
        "method": "KG-BERT (HF cross-encoder)",
        "data_dir": args.data_dir,
        "model_name": args.model_name,
        "device": device,
        "seed": args.seed,
        "params": {
            "epochs": args.epochs,
            "lr": args.lr,
            "train_batch": args.train_batch,
            "eval_batch": args.eval_batch,
            "max_len": args.max_len,
            "neg_per_pos": args.neg_per_pos,
            "eval_every": args.eval_every
        },
        "best_dev_mrr": best_dev_mrr,
        "history": history,
        "timestamp_unix": int(time.time())
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("Saved:", out_path)

if __name__ == "__main__":
    main()
