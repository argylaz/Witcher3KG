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


def make_labeled_samples(pos_df, all_true_set, entities, ent2desc, rel2desc, neg_per_pos=5, seed=42):
    rng = random.Random(seed)
    samples = []
    for _, row in pos_df.iterrows():
        h, r, t = row["h"], row["r"], row["t"]
        
        def get_pair(head, rel, tail):
            # Sentence A: Head Description + Relation Description
            text_a = f"{ent2desc.get(head, head)} {rel2desc.get(rel, rel)}"
            # Sentence B: Tail Description
            text_b = ent2desc.get(tail, tail)
            return (text_a, text_b)

        # Positive
        samples.append((get_pair(h, r, t), 1))

        # Negatives
        for _ in range(neg_per_pos):
            if rng.random() < 0.5:
                # Corrupt Tail
                tt = rng.choice(entities)
                while (h, r, tt) in all_true_set: tt = rng.choice(entities)
                samples.append((get_pair(h, r, tt), 0))
            else:
                # Corrupt Head
                hh = rng.choice(entities)
                while (hh, r, t) in all_true_set: hh = rng.choice(entities)
                # For KG-BERT, if we corrupt Head, the new Head goes into Sentence A
                samples.append((get_pair(hh, r, t), 0))

    return samples

class TextClsDataset(Dataset):
    def __init__(self, samples):
        self.samples = samples
    def __len__(self):
        return len(self.samples)
    def __getitem__(self, idx):
        return self.samples[idx]

def collate_fn(batch, tokenizer, max_len):
    # Batch is now a list of ((text_a, text_b), label)
    inputs_labels = zip(*batch)
    inputs, labels = inputs_labels
    
    # Unpack the pairs
    text_a = [i[0] for i in inputs]
    text_b = [i[1] for i in inputs]
    
    # Tokenize as a pair
    enc = tokenizer(
        text=text_a,
        text_pair=text_b, 
        padding=True, 
        truncation=True, 
        max_length=max_len, 
        return_tensors="pt"
    )
    return enc, torch.tensor(labels, dtype=torch.long)

@torch.inference_mode()
def predict_probs(model, tokenizer, texts, device, batch_size=64, max_len=256):
    model.eval()
    probs = []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i+batch_size]
        enc = tokenizer(chunk, padding=True, truncation=True, max_length=max_len, return_tensors="pt")
        enc = {k: v.to(device, non_blocking=True) for k, v in enc.items()}
        logits = model(**enc).logits
        p = torch.softmax(logits, dim=-1)[:, 1]  # P(label=1)
        probs.append(p.detach().cpu())
    return torch.cat(probs, dim=0).numpy()

def classification_metrics(y_true, y_prob, threshold=0.5):
    # y_true: list/int array of 0/1
    # y_prob: probabilities for class 1
    y_true = list(map(int, y_true))
    y_pred = [1 if p >= threshold else 0 for p in y_prob]

    tp = sum((yt==1 and yp==1) for yt, yp in zip(y_true, y_pred))
    tn = sum((yt==0 and yp==0) for yt, yp in zip(y_true, y_pred))
    fp = sum((yt==0 and yp==1) for yt, yp in zip(y_true, y_pred))
    fn = sum((yt==1 and yp==0) for yt, yp in zip(y_true, y_pred))

    acc = (tp + tn) / max(1, (tp + tn + fp + fn))
    prec = tp / max(1, (tp + fp))
    rec  = tp / max(1, (tp + fn))
    f1 = 0.0 if (prec + rec) == 0 else (2 * prec * rec) / (prec + rec)

    return {
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "threshold": threshold
    }

def eval_triple_classification(model, tokenizer, pos_df, all_true_set, entities, ent2desc, rel2desc,
                               device, eval_batch, max_len, neg_per_pos, seed, threshold):
    samples = make_labeled_samples(
        pos_df=pos_df,
        all_true_set=all_true_set,
        entities=entities,
        ent2desc=ent2desc,
        rel2desc=rel2desc,
        neg_per_pos=neg_per_pos,
        seed=seed
    )
    texts = [s[0] for s in samples]
    labels = [s[1] for s in samples]

    probs = predict_probs(model, tokenizer, texts, device, batch_size=eval_batch, max_len=max_len)
    metrics = classification_metrics(labels, probs, threshold=threshold)

    metrics.update({
        "num_pos": int(sum(labels)),
        "num_neg": int(len(labels) - sum(labels)),
        "num_total": int(len(labels)),
        "neg_per_pos": int(neg_per_pos),
        "neg_seed": int(seed)
    })
    return metrics

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
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--out_dir", default="results")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    use_amp = (device == "cuda")
    set_seed(args.seed)

    ent2desc, rel2desc, entities = read_maps(args.data_dir)
    train_df = load_triples(os.path.join(args.data_dir, "train.tsv"))
    dev_df   = load_triples(os.path.join(args.data_dir, "dev.tsv"))
    test_df  = load_triples(os.path.join(args.data_dir, "test.tsv"))

    # used only to avoid sampling a negative that is actually true anywhere
    all_true_set = set(map(tuple, pd.concat([train_df, dev_df, test_df])[["h","r","t"]].values.tolist()))

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = AutoModelForSequenceClassification.from_pretrained(args.model_name, num_labels=2).to(device)

    # Build training samples once for simplicity
    train_samples = make_labeled_samples(
        pos_df=train_df,
        all_true_set=all_true_set,
        entities=entities,
        ent2desc=ent2desc,
        rel2desc=rel2desc,
        neg_per_pos=args.neg_per_pos,
        seed=args.seed)
    train_ds = TextClsDataset(train_samples)
    loader = DataLoader(
        train_ds,
        batch_size=args.train_batch,
        shuffle=True,
        pin_memory=(device == "cuda"),
        collate_fn=lambda b: collate_fn(b, tokenizer, args.max_len))

    optim = AdamW(model.parameters(), lr=args.lr)
    scaler = GradScaler(enabled=use_amp)

    best_dev_f1 = -1.0
    best_ckpt_dir = os.path.join("checkpoints_kgbert_cls", args.run_name, "best")
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
            dev_metrics = eval_triple_classification(
                model, tokenizer, dev_df, all_true_set, entities, ent2desc, rel2desc,
                device=device, eval_batch=args.eval_batch, max_len=args.max_len,
                neg_per_pos=args.neg_per_pos, seed=args.seed + 1000, threshold=args.threshold
            )
            history["dev"].append({"epoch": ep, **dev_metrics})
            print(f"[{args.run_name}] DEV (triple classification) {dev_metrics}")

            # Select best model by dev F1
            if dev_metrics["f1"] > best_dev_f1:
                best_dev_f1 = dev_metrics["f1"]
                model.save_pretrained(best_ckpt_dir)
                tokenizer.save_pretrained(best_ckpt_dir)

    # load best and eval on test
    best_model = AutoModelForSequenceClassification.from_pretrained(best_ckpt_dir).to(device)
    best_tok = AutoTokenizer.from_pretrained(best_ckpt_dir)

    test_metrics = eval_triple_classification(
        best_model, best_tok, test_df, all_true_set, entities, ent2desc, rel2desc,
        device=device, eval_batch=args.eval_batch, max_len=args.max_len,
        neg_per_pos=args.neg_per_pos, seed=args.seed + 2000, threshold=args.threshold)
    history["test"] = test_metrics
    print(f"[{args.run_name}] TEST (triple classification) {test_metrics}")

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, f"{args.run_name}.json")

    payload = {
        "run_name": args.run_name,
        "task": "TRIPLE_CLASSIFICATION",
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
            "eval_every": args.eval_every,
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
