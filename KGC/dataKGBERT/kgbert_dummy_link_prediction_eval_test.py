import os, json, time
import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# paths
from pathlib import Path
REPO = Path("/content/drive/MyDrive/Witcher3KG/KGC")
KGBERT_DATA = REPO / "dataKGBERT"
OUT_DIR = KGBERT_DATA / "results"
OUT_DIR.mkdir(exist_ok=True)

device = "cuda" if torch.cuda.is_available() else "cpu"
print("Device:", device)

# ---------- helpers (same logic as your script) ----------
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

@torch.inference_mode()
def score_texts(model, tokenizer, texts, device, batch_size=64, max_len=256):
    model.eval()
    scores = []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i+batch_size]
        enc = tokenizer(chunk, padding=True, truncation=True, max_length=max_len, return_tensors="pt")
        enc = {k: v.to(device) for k, v in enc.items()}
        logits = model(**enc).logits
        prob_pos = torch.softmax(logits, dim=-1)[:, 1]
        scores.append(prob_pos.detach().cpu())
    return torch.cat(scores, dim=0).numpy()

def filtered_link_prediction_eval(model, tokenizer, df, all_true, entities, ent2desc, rel2desc, device, eval_batch, max_len):
    ranks = []
    for _, row in df.iterrows():
        h, r, t = row["h"], row["r"], row["t"]

        # tail prediction
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

        # head prediction
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

# ---------- load data ----------
data_dir = str(KGBERT_DATA)

train_df = load_triples(os.path.join(data_dir, "train.tsv"))
dev_df   = load_triples(os.path.join(data_dir, "dev.tsv"))
test_df  = load_triples(os.path.join(data_dir, "test.tsv"))
test_df = test_df.head(5).copy()
all_true = set(map(tuple, pd.concat([train_df, dev_df, test_df])[["h","r","t"]].values.tolist()))

ent2desc, rel2desc, entities = read_maps(data_dir)

print("Triples:", len(train_df), len(dev_df), len(test_df))
print("Entities:", len(entities))

# ---------- load model (NO TRAINING) ----------
model_name = "bert-base-uncased"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=2).to(device)

# ---------- run dummy eval ----------
metrics = filtered_link_prediction_eval(
    model, tokenizer, test_df, all_true, entities, ent2desc, rel2desc,
    device=device, eval_batch=64, max_len=256
)
print("DUMMY TEST METRICS:", metrics)

# ---------- save ----------
out_path = OUT_DIR / "kgbert_dummy.json"
payload = {
    "run_name": "kgbert_dummy",
    "note": "Eval-only sanity check with pretrained BERT + random classification head (no fine-tuning). Metrics are not meaningful.",
    "data_dir": str(KGBERT_DATA),
    "model_name": model_name,
    "device": device,
    "metrics": metrics,
    "timestamp_unix": int(time.time())
}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

print("Saved:", out_path)
