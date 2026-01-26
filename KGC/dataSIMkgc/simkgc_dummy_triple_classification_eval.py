import os, json, time, random, argparse
import pandas as pd
import torch
import torch.nn as nn
from transformers import AutoTokenizer, AutoModel

def set_seed(seed: int):
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

def load_triples_jsonl(path):
    #Loads triples from a jsonl file
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
    return f"{ent2desc.get(h,h)} {rel2desc.get(r,r)}" #Space separator
def build_entity_text(e, ent2desc):
    return ent2desc.get(e, e)

def make_labeled_samples(pos_df, all_true_set, entities, neg_per_pos=1, seed=42):
    #Lists from (h, r, t, label) tuples.
    rng = random.Random(seed)#random
    samples = []
    for _, row in pos_df.iterrows():
        h, r, t = row["h"], row["r"], row["t"]
        #positives
        samples.append((h, r, t, 1))
        #negatives-corruptions
        for _ in range(neg_per_pos):
            if rng.random() < 0.5:
                #corrupt tail
                tt = rng.choice(entities)
                while (h, r, tt) in all_true_set:
                    tt = rng.choice(entities)
                samples.append((h, r, tt, 0))
            else:
                #corrupt head
                hh = rng.choice(entities)
                while (hh, r, t) in all_true_set:
                    hh = rng.choice(entities)
                samples.append((hh, r, t, 0))
    return samples

class BiEncoder(nn.Module):
    def __init__(self, model_name):#call the pretrained model
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
def predict_similarity(model, tokenizer, samples, ent2desc, rel2desc, device, batch_size=64, max_len=256):
    model.eval()
    sim_scores = []
    #samples is list of (h, r, t, label)
    for i in range(0, len(samples), batch_size):
        batch = samples[i:i+batch_size]
        hs, rs, ts, _ = zip(*batch)
        #Prepare texts
        q_texts = [build_query_text(h, r, ent2desc, rel2desc) for h, r in zip(hs, rs)]
        t_texts = [build_entity_text(t, ent2desc) for t in ts]
        #Tokenizing
        q_enc = tokenizer(q_texts, padding=True, truncation=True, max_length=max_len, return_tensors="pt")#return_tensors="pt" returns torch.Tensor instead of lists
        t_enc = tokenizer(t_texts, padding=True, truncation=True, max_length=max_len, return_tensors="pt")
        q_enc = {k: v.to(device) for k, v in q_enc.items()}
        t_enc = {k: v.to(device) for k, v in t_enc.items()}
        #Encoding
        q_emb = model.encode(q_enc) #[B, D]
        t_emb = model.encode(t_enc) #[B, D]
        #dot product is Cosine Similarity, because of L2 normalisation
        cosine = torch.sum(q_emb * t_emb, dim=-1) #[B] because of L2 (q·t) / (||q||·||t||) = q·t  and dim=-1 sums over D
        sim_scores.append(cosine.cpu())
    return torch.cat(sim_scores, dim=0).numpy()

def classification_metrics(y_true, y_scores, threshold=0.5):
    y_true = list(map(int, y_true))
    #If Cosine Similarity > threshold then predict 1 meaning true
    y_pred = [1 if s >= threshold else 0 for s in y_scores]
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
    ap.add_argument("--run_name", default="simkgc_dummy_baseline")
    ap.add_argument("--model_name", default="bert-base-uncased")
    ap.add_argument("--eval_batch", type=int, default=64)
    ap.add_argument("--max_len", type=int, default=512)
    ap.add_argument("--neg_per_pos", type=int, default=1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--threshold", type=float, default=0.5)#For Cosine Similarity
    ap.add_argument("--out_dir", default="results")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Running SimKGC Dummy Baseline on {device}.")
    set_seed(args.seed)

    ent2desc, rel2desc, entities = load_maps(args.data_dir)
    train_df = load_triples_jsonl(os.path.join(args.data_dir, "train.jsonl"))
    dev_path = os.path.join(args.data_dir, "dev.jsonl")
    dev_df = load_triples_jsonl(dev_path)
    test_df = load_triples_jsonl(os.path.join(args.data_dir, "test.jsonl"))

    all_true_set = set(map(tuple, pd.concat([train_df, dev_df, test_df])[["h","r","t"]].values.tolist()))
    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = BiEncoder(args.model_name).to(device)
    #Create Samples (True + Negatives)
    samples = make_labeled_samples(test_df, all_true_set, entities, neg_per_pos=args.neg_per_pos, seed=args.seed + 2000)
    labels = [s[3] for s in samples]
    print(f"Evaluating on {len(samples)} test samples.")

    scores = predict_similarity(model, tokenizer, samples, ent2desc, rel2desc, device, args.eval_batch, args.max_len)
    metrics = classification_metrics(labels, scores, threshold=args.threshold)
    metrics.update({
        "num_pos": int(sum(labels)),
        "num_neg": int(len(labels) - sum(labels)),
        "num_total": int(len(labels))})
    print("------------------------------------------------")
    print("UNTRAINED (DUMMY) BASELINE METRICS:")
    print(json.dumps(metrics, indent=2))
    print("------------------------------------------------")
    #Save JSON
    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, f"{args.run_name}.json")
    payload = {
        "run_name": args.run_name,
        "task": "TRIPLE_CLASSIFICATION_BASELINE",
        "method": "Untrained SimKGC (Bi-Encoder)",
        "model_name": args.model_name,
        "metrics": metrics,
        "timestamp_unix": int(time.time())}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("Saved Baseline Results:", out_path)
if __name__ == "__main__":
    main()