# scripts/make_dataset_ready.py
import os
import json
import argparse
import pandas as pd

def drop_header_if_present(df: pd.DataFrame) -> pd.DataFrame:
    first = str(df.iloc[0, 0]).strip().lower()
    if first in {"uri", "entity", "relation", "head"}:
        return df.iloc[1:].reset_index(drop=True)
    return df

def read_triples(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t", header=None, names=["h","r","t"]).dropna()
    if df.shape[1] != 3:
        raise ValueError(f"Expected 3 columns in triples: {path}")
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_dir", required=True, help="Folder containing train/valid/test and desc tsvs")
    ap.add_argument("--train_file", default="train.tsv")
    ap.add_argument("--valid_file", default="valid.tsv")
    ap.add_argument("--test_file", default="test.tsv")
    ap.add_argument("--entity_desc", default="entity_desc.tsv")
    ap.add_argument("--relation_desc", default="relation_desc.tsv")
    args = ap.parse_args()

    data_dir = args.data_dir

    train_path = os.path.join(data_dir, args.train_file)
    valid_path = os.path.join(data_dir, args.valid_file)
    test_path  = os.path.join(data_dir, args.test_file)

    ent_desc_path = os.path.join(data_dir, args.entity_desc)
    rel_desc_path = os.path.join(data_dir, args.relation_desc)

    # 1) Ensure dev.tsv exists (copy valid -> dev)
    dev_path = os.path.join(data_dir, "dev.tsv")
    if not os.path.exists(dev_path):
        with open(valid_path, "rb") as fsrc, open(dev_path, "wb") as fdst:
            fdst.write(fsrc.read())

    # 2) Load triples to build entities/relations
    train_df = read_triples(train_path)
    dev_df   = read_triples(dev_path)
    test_df  = read_triples(test_path)
    all_df   = pd.concat([train_df, dev_df, test_df], ignore_index=True).drop_duplicates()

    entities = sorted(set(all_df["h"]).union(set(all_df["t"])))
    relations = sorted(set(all_df["r"]))

    # 3) Create entity2textlong.tsv (no header)
    ent = pd.read_csv(ent_desc_path, sep="\t", header=None)
    ent = drop_header_if_present(ent)
    ent.columns = ["uri", "description"]
    ent = ent.dropna().drop_duplicates(subset=["uri"])

    out_ent_path = os.path.join(data_dir, "entity2textlong.tsv")
    ent[["uri","description"]].to_csv(out_ent_path, sep="\t", header=False, index=False)

    # 4) Create relation2text.txt (no header) + ensure coverage
    rel = pd.read_csv(rel_desc_path, sep="\t", header=None)
    rel = drop_header_if_present(rel)
    rel.columns = ["uri", "description"]
    rel = rel.dropna().drop_duplicates(subset=["uri"])

    rel_map = dict(zip(rel["uri"], rel["description"]))
    missing = [r for r in relations if r not in rel_map]
    if missing:
        for ruri in missing:
            local = ruri.split("#")[-1] if "#" in ruri else ruri.rsplit("/", 1)[-1]
            rel_map[ruri] = f"Relation '{local}' connecting a head entity to a tail entity."
        rel = pd.DataFrame({"uri": list(rel_map.keys()), "description": list(rel_map.values())})

    out_rel_path = os.path.join(data_dir, "relation2text.txt")
    rel[["uri","description"]].to_csv(out_rel_path, sep="\t", header=False, index=False)

    # 5) entities.txt / relations.txt
    with open(os.path.join(data_dir, "entities.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(entities))
    with open(os.path.join(data_dir, "relations.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(relations))

    # 6) meta.json (useful for report)
    meta = {
        "counts": {
            "train_triples": int(train_df.shape[0]),
            "dev_triples": int(dev_df.shape[0]),
            "test_triples": int(test_df.shape[0]),
            "all_unique_triples": int(all_df.shape[0]),
            "entities": int(len(entities)),
            "relations": int(len(relations)),
        },
        "files": {
            "train": args.train_file,
            "valid": args.valid_file,
            "dev": "dev.tsv",
            "test": args.test_file,
            "entity_desc": args.entity_desc,
            "relation_desc": args.relation_desc,
            "entity2textlong": "entity2textlong.tsv",
            "relation2text": "relation2text.txt",
            "entities_list": "entities.txt",
            "relations_list": "relations.txt"
        }
    }
    with open(os.path.join(data_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print("Dataset ready:", data_dir)
    print(json.dumps(meta["counts"], indent=2))

if __name__ == "__main__":
    main()
