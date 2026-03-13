import os, json, time, random, argparse
import pandas as pd
import torch
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
        samples.append((triple_to_text(h, r, t, ent2desc, rel2desc), 1))
        for _ in range(neg_per_pos):
            if rng.random() < 0.5:
                tt = rng.choice(entities)
                while (h, r, tt) in all_true_set: tt = rng.choice(entities)
                samples.append((triple_to_text(h, r, tt, ent2desc, rel2desc), 0))
            else:
                hh = rng.choice(entities)
                while (hh, r, t) in all_true_set: hh = rng.choice(entities)
                samples.append((triple_to_text(hh, r, t, ent2desc, rel2desc), 0))
    return samples

@torch.inference_mode()
def predict_probs(model, tokenizer, texts, device, batch_size=64, max_len=256):
    model.eval()
    probs = []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i+batch_size]
        enc = tokenizer(chunk, padding=True, truncation=True, max_length=max_len, return_tensors="pt")
        enc = {k: v.to(device) for k, v in enc.items()}
        logits = model(**enc).logits
        p = torch.softmax(logits, dim=-1)[:, 1]
        probs.append(p.detach().cpu())
    return torch.cat(probs, dim=0).numpy()

def classification_metrics(y_true, y_prob, threshold=0.5):
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
        "accuracy": acc, "precision": prec, "recall": rec, "f1": f1,
        "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "threshold": threshold}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_dir", required=True)
    ap.add_argument("--run_name", default="kgbert_dummy_baseline")
    ap.add_argument("--model_name", default="bert-base-uncased")
    ap.add_argument("--eval_batch", type=int, default=64)
    ap.add_argument("--max_len", type=int, default=256)
    ap.add_argument("--neg_per_pos", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--out_dir", default="results")
    args = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Running Dummy Baseline on {device}.")
    set_seed(args.seed)

    ent2desc, rel2desc, entities = read_maps(args.data_dir)
    train_df = load_triples(os.path.join(args.data_dir, "train.tsv"))
    dev_path = os.path.join(args.data_dir, "dev.tsv")
    if not os.path.exists(dev_path): dev_path = os.path.join(args.data_dir, "valid.tsv")
    dev_df = load_triples(dev_path)
    test_df = load_triples(os.path.join(args.data_dir, "test.tsv"))

    all_true_set = set(map(tuple, pd.concat([train_df, dev_df, test_df])[["h","r","t"]].values.tolist()))

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = AutoModelForSequenceClassification.from_pretrained(args.model_name, num_labels=2).to(device)

    samples = make_labeled_samples(
        test_df, all_true_set, entities, ent2desc, rel2desc, 
        neg_per_pos=args.neg_per_pos, seed=args.seed + 2000)
    texts = [s[0] for s in samples]
    labels = [s[1] for s in samples]
    print(f"Evaluating on {len(texts)} test samples.")

    probs = predict_probs(model, tokenizer, texts, device, args.eval_batch, args.max_len)
    metrics = classification_metrics(labels, probs, threshold=args.threshold)
    metrics.update({
        "num_pos": int(sum(labels)),
        "num_neg": int(len(labels) - sum(labels)),
        "num_total": int(len(labels))})
    print("-" * 40)
    print("ZERO-SHOT (DUMMY) BASELINE METRICS:")
    print(json.dumps(metrics, indent=2))
    print("-" * 40)
    #Save JSON
    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, f"{args.run_name}.json")
    payload = {
        "run_name": args.run_name,
        "task": "TRIPLE_CLASSIFICATION_BASELINE",
        "method": "Zero-Shot BERT (No Training)",
        "model_name": args.model_name,
        "metrics": metrics,
        "timestamp_unix": int(time.time())}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("Saved Baseline Results:", out_path)
if __name__ == "__main__":
    main()