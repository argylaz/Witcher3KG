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

def load_triples(path):
    return pd.read_csv(path, sep="\t", header=None, names=["h","r","t"]).dropna()

def load_maps(data_dir):
    ent = pd.read_csv(os.path.join(data_dir, "entity2textlong.tsv"), sep="\t", header=None, names=["uri","desc"])
    rel = pd.read_csv(os.path.join(data_dir, "relation2text.txt"), sep="\t", header=None, names=["uri","desc"])
    ent2desc = dict(zip(ent["uri"], ent["desc"]))
    rel2desc = dict(zip(rel["uri"], rel["desc"]))
    entities = open(os.path.join(data_dir, "entities.txt"), encoding="utf-8").read().splitlines()
    return ent2desc, rel2desc, entities

def build_query_text(h, r, ent2desc, rel2desc):
    return f"{ent2desc.get(h,h)}\n{rel2desc.get(r,r)}"

def build_entity_text(e, ent2desc):
    return ent2desc.get(e, e)

class TriplesDataset(Dataset):
    def __init__(self, df):
        self.df = df.reset_index(drop=True)

    def __len__(self): 
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        return row["h"], row["r"], row["t"]

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

def collate(batch, tokenizer, ent2desc, rel2desc, max_len):
    hs, rs, ts = zip(*batch)
    q_texts = [build_query_text(h, r, ent2desc, rel2desc) for h, r in zip(hs, rs)]
    t_texts = [build_entity_text(t, ent2desc) for t in ts]
    q_enc = tokenizer(q_texts, padding=True, truncation=True, max_length=max_len, return_tensors="pt")
    t_enc = tokenizer(t_texts, padding=True, truncation=True, max_length=max_len, return_tensors="pt")
    return q_enc, t_enc

@torch.inference_mode()
def encode_all_entities(model, tokenizer, entities, ent2desc, device, max_len, batch_size=64):
    model.eval()
    texts = [build_entity_text(e, ent2desc) for e in entities]
    embs = []
    for i in range(0, len(texts), batch_size):
        enc = tokenizer(texts[i:i+batch_size], padding=True, truncation=True, max_length=max_len, return_tensors="pt")
        enc = {k: v.to(device, non_blocking=True) for k, v in enc.items()}
        embs.append(model.encode(enc).cpu())
    return torch.cat(embs, dim=0)  # [N,D]

@torch.inference_mode()
def filtered_eval(model, tokenizer, df, all_true, entities, ent2desc, rel2desc, device, max_len, batch_size=64):
    model.eval()
    ent_emb = encode_all_entities(model, tokenizer, entities, ent2desc, device, max_len, batch_size)
    ent2idx = {e: i for i, e in enumerate(entities)}

    ranks = []
    for _, row in df.iterrows():
        h, r, t = row["h"], row["r"], row["t"]

        # tail prediction
        qtext = build_query_text(h, r, ent2desc, rel2desc)
        qenc = tokenizer([qtext], padding=True, truncation=True, max_length=max_len, return_tensors="pt")
        qenc = {k: v.to(device, non_blocking=True) for k, v in qenc.items()}
        q = model.encode(qenc).cpu()[0]
        scores = (ent_emb @ q).numpy()
        for e in entities:
            if e != t and (h, r, e) in all_true:
                scores[ent2idx[e]] = -1e9
        ranks.append(1 + int((scores > scores[ent2idx[t]]).sum()))

        # head prediction (simple symmetric query baseline)
        qtext = build_query_text(t, r, ent2desc, rel2desc)
        qenc = tokenizer([qtext], padding=True, truncation=True, max_length=max_len, return_tensors="pt")
        qenc = {k: v.to(device, non_blocking=True) for k, v in qenc.items()}
        q = model.encode(qenc).cpu()[0]
        scores = (ent_emb @ q).numpy()
        for e in entities:
            if e != h and (e, r, t) in all_true:
                scores[ent2idx[e]] = -1e9
        ranks.append(1 + int((scores > scores[ent2idx[h]]).sum()))

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
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch_size", type=int, default=32)
    ap.add_argument("--max_len", type=int, default=256)
    ap.add_argument("--temperature", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--eval_every", type=int, default=1)
    ap.add_argument("--out_dir", default="results")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    use_amp = (device == "cuda")
    set_seed(args.seed)

    ent2desc, rel2desc, entities = load_maps(args.data_dir)
    train_df = load_triples(os.path.join(args.data_dir, "train.tsv"))
    dev_df   = load_triples(os.path.join(args.data_dir, "dev.tsv"))
    test_df  = load_triples(os.path.join(args.data_dir, "test.tsv"))
    all_true = set(map(tuple, pd.concat([train_df, dev_df, test_df])[["h","r","t"]].values.tolist()))

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = BiEncoder(args.model_name).to(device)
    optim = AdamW(model.parameters(), lr=args.lr)
    scaler = GradScaler(enabled=use_amp)

    ds = TriplesDataset(train_df)
    loader = DataLoader(
        ds,
        batch_size=args.batch_size,
        shuffle=True,
        pin_memory=(device == "cuda"),
        collate_fn=lambda b: collate(b, tokenizer, ent2desc, rel2desc, args.max_len),
    )

    best_dev_mrr = -1.0
    best_ckpt_dir = os.path.join("checkpoints_simkgc", args.run_name, "best")
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
            dev_metrics = filtered_eval(
                model, tokenizer, dev_df, all_true, entities, ent2desc, rel2desc,
                device=device, max_len=args.max_len, batch_size=64
            )
            history["dev"].append({"epoch": ep, **dev_metrics})
            print(f"[{args.run_name}] DEV {dev_metrics}")

            if dev_metrics["MRR"] > best_dev_mrr:
                best_dev_mrr = dev_metrics["MRR"]
                torch.save(model.state_dict(), os.path.join(best_ckpt_dir, "model.pt"))
                tokenizer.save_pretrained(best_ckpt_dir)

    # load best and eval on test
    best_model = BiEncoder(args.model_name).to(device)
    best_model.load_state_dict(torch.load(os.path.join(best_ckpt_dir, "model.pt"), map_location=device))
    best_tok = AutoTokenizer.from_pretrained(best_ckpt_dir)

    test_metrics = filtered_eval(
        best_model, best_tok, test_df, all_true, entities, ent2desc, rel2desc,
        device=device, max_len=args.max_len, batch_size=64
    )
    history["test"] = test_metrics
    print(f"[{args.run_name}] TEST {test_metrics}")

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, f"{args.run_name}.json")
    payload = {
        "run_name": args.run_name,
        "method": "SimKGC-style (bi-encoder contrastive)",
        "data_dir": args.data_dir,
        "model_name": args.model_name,
        "device": device,
        "seed": args.seed,
        "params": {
            "epochs": args.epochs,
            "lr": args.lr,
            "batch_size": args.batch_size,
            "max_len": args.max_len,
            "temperature": args.temperature,
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

