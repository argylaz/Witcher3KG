# scripts/make_dataset_ready.py
import os
import json
import argparse
import pandas as pd

def drop_header_if_present(df: pd.DataFrame) -> pd.DataFrame:
    #cleans header
    if df.empty: return df
    first = str(df.iloc[0, 0]).strip().lower()
    if first in {"uri", "entity", "relation", "head"}:
        return df.iloc[1:].reset_index(drop=True)
    return df

def read_triples(path: str) -> pd.DataFrame:
    try:#if headers exist it does not take them
        df = pd.read_csv(path, sep="\t", header=None, names=["h","r","t"])
        if str(df.iloc[0]["h"]).strip().lower() in ["h", "head", "subject", "source"]:
            df = df.iloc[1:]
        return df.dropna()
    except Exception as e:
        print(f"Warning: Could not read {path}. Error: {e}")
        return pd.DataFrame(columns=["h","r","t"])

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
    print(f"Processing data in: {data_dir}")

    #1)Ensure dev.tsv exists (copy valid to dev)
    dev_path = os.path.join(data_dir, "dev.tsv")
    if not os.path.exists(dev_path) and os.path.exists(valid_path):
        print("Creating dev.tsv from valid.tsv...")
        with open(valid_path, "rb") as fsrc, open(dev_path, "wb") as fdst:
            fdst.write(fsrc.read())

    #2) Load triples to build entities/relations
    print("Loading triples...")
    train_df = read_triples(train_path)
    dev_df = read_triples(dev_path)
    test_df = read_triples(test_path)
    #concatenate all to find unique instances
    all_df = pd.concat([train_df, dev_df, test_df], ignore_index=True).drop_duplicates()

    #real entities and relations of the dataset
    entities = sorted(list(set(all_df["h"]).union(set(all_df["t"]))))
    relations = sorted(list(set(all_df["r"])))
    print(f"Found {len(entities)} unique entities and {len(relations)} unique relations in triples.")
    
    #3) Create entity2textlong.tsv (Aligned with entities list)
    print("Processing Entity Descriptions...")
    ent = pd.read_csv(ent_desc_path, sep="\t", header=None)
    ent = drop_header_if_present(ent)
    ent.columns = ["uri", "description"]
    ent = ent.dropna().drop_duplicates(subset=["uri"])
    
    #Filtering only entities that exist in the triples
    ent_map = dict(zip(ent["uri"], ent["description"]))
    final_ent_data = []
    for e in entities:
        desc = ent_map.get(e, f"Entity {e.split('/')[-1]}")
        final_ent_data.append({"uri": e, "description": desc})

    final_ent_df = pd.DataFrame(final_ent_data)
    out_ent_path = os.path.join(data_dir, "entity2textlong.tsv")
    final_ent_df.to_csv(out_ent_path, sep="\t", header=False, index=False)

    #4) Create relation2text.txt (Aligned with relations list)
    print("Processing Relation Descriptions...")
    rel = pd.read_csv(rel_desc_path, sep="\t", header=None)
    rel = drop_header_if_present(rel)
    rel.columns = ["uri", "description"]
    rel = rel.dropna().drop_duplicates(subset=["uri"])
    rel_map = dict(zip(rel["uri"], rel["description"]))

    #checking remaining
    unused_rels = set(rel_map.keys()) - set(relations)
    if unused_rels:
        print(f"Note: Ignoring {len(unused_rels)} relations present in desc but not in triples (e.g., {list(unused_rels)[0]})")
    final_rel_data = []
    for r in relations:
        if r in rel_map:
            desc = rel_map[r]
        else:
            #Generate default description if missing
            local = r.split("#")[-1] if "#" in r else r.rsplit("/", 1)[-1]
            desc = f"Relation '{local}' connecting a head entity to a tail entity."
            print(f"Warning: No description for used relation '{r}'. Using default.")
        final_rel_data.append({"uri": r, "description": desc})
    final_rel_df = pd.DataFrame(final_rel_data)
    out_rel_path = os.path.join(data_dir, "relation2text.txt")
    final_rel_df.to_csv(out_rel_path, sep="\t", header=False, index=False)

    #5) Save entities.txt / relations.txt
    print("Saving lists...")
    with open(os.path.join(data_dir, "entities.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(entities))
    with open(os.path.join(data_dir, "relations.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(relations))

    #6) meta.json
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
    print("-" * 30)
    print("Dataset Ready!")
    print(json.dumps(meta["counts"], indent=2))
if __name__ == "__main__":
    main()