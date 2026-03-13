import os
import json
import argparse
import pandas as pd

def read_jsonl_triples(path: str) -> pd.DataFrame:
    #Reads triples from a jsonl file
    data = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line)
                if "head" in obj and "relation" in obj and "tail" in obj:
                    data.append({
                        "h": obj["head"],
                        "r": obj["relation"],
                        "t": obj["tail"]})
        return pd.DataFrame(data)
    except Exception as e:
        print(f"Warning: Could not read {path}. Error: {e}")
        return pd.DataFrame(columns=["h", "r", "t"])
    
def drop_header_if_present(df: pd.DataFrame)->pd.DataFrame:
    if df.empty: return df
    first = str(df.iloc[0, 0]).strip().lower()
    if first in {"uri", "entity", "relation", "head"}:
        return df.iloc[1:].reset_index(drop=True)
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_dir", required=True)
    ap.add_argument("--train_file", default="train.jsonl")
    ap.add_argument("--valid_file", default="valid.jsonl")
    ap.add_argument("--test_file", default="test.jsonl")
    ap.add_argument("--entity_desc", default="entity_desc.tsv")
    ap.add_argument("--relation_desc", default="relation_desc.tsv")
    args = ap.parse_args()

    data_dir = args.data_dir
    print(f"Processing SimKGC data in: {data_dir}")
    #paths
    train_path = os.path.join(data_dir, args.train_file)
    valid_path = os.path.join(data_dir, args.valid_file)
    test_path  = os.path.join(data_dir, args.test_file)
    dev_path = os.path.join(data_dir, "dev.jsonl")
    if not os.path.exists(dev_path) and os.path.exists(valid_path):
        print("Creating dev.jsonl from valid.jsonl...")
        with open(valid_path, "rb") as fsrc, open(dev_path, "wb") as fdst:
            fdst.write(fsrc.read())
    #json triples
    print("Loading JSONL triples...")
    train_df = read_jsonl_triples(train_path)
    dev_df   = read_jsonl_triples(dev_path)
    test_df  = read_jsonl_triples(test_path)
    all_df = pd.concat([train_df, dev_df, test_df], ignore_index=True).drop_duplicates()
    entities = sorted(list(set(all_df["h"]).union(set(all_df["t"]))))
    relations = sorted(list(set(all_df["r"])))
    print(f"Found {len(entities)} unique entities and {len(relations)} unique relations.")

    #Entity descriptions
    ent_desc_path = os.path.join(data_dir, args.entity_desc)
    print("Processing entity descriptions...")
    ent = pd.read_csv(ent_desc_path, sep="\t", header=None)
    ent = drop_header_if_present(ent)
    ent.columns = ["uri", "description"]
    ent = ent.dropna().drop_duplicates(subset=["uri"])
    
    ent_map = dict(zip(ent["uri"], ent["description"]))
    final_ent_data = []
    for e in entities:
        desc = ent_map.get(e, f"Entity {e.split('/')[-1]}")
        final_ent_data.append({"uri": e, "description": desc})
    pd.DataFrame(final_ent_data).to_csv(os.path.join(data_dir, "entity2textlong.tsv"),
                                        sep="\t", header=False, index=False)

    #Relation descriptions(same code as entities)
    rel_desc_path = os.path.join(data_dir, args.relation_desc)
    print("Processing relation descriptions...")
    rel = pd.read_csv(rel_desc_path, sep="\t", header=None)
    rel = drop_header_if_present(rel)
    rel.columns = ["uri", "description"]
    rel = rel.dropna().drop_duplicates(subset=["uri"])
    
    rel_map = dict(zip(rel["uri"], rel["description"]))
    final_rel_data = []
    for r in relations:
        desc = rel_map.get(r, f"Relation {r.split('/')[-1]}")
        final_rel_data.append({"uri": r, "description": desc})
    pd.DataFrame(final_rel_data).to_csv(os.path.join(data_dir, "relation2text.txt"),
                                        sep="\t", header=False, index=False)
    #Saving lists
    with open(os.path.join(data_dir, "entities.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(entities))
    with open(os.path.join(data_dir, "relations.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(relations))

    #Metadata json
    meta = {
        "counts": {
            "train_triples": int(train_df.shape[0]),
            "dev_triples": int(dev_df.shape[0]),
            "test_triples": int(test_df.shape[0]),
            "entities": int(len(entities)),
            "relations": int(len(relations)),
        },
        "files": {
            "train": args.train_file,
            "dev": "dev.jsonl",
            "test": args.test_file,
            "entity2textlong": "entity2textlong.tsv",
            "relation2text": "relation2text.txt",
            "entities_list": "entities.txt"
        }
    }
    with open(os.path.join(data_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print("SimKGC Dataset Ready!")
    print(json.dumps(meta["counts"], indent=2))

if __name__ == "__main__":
    main()