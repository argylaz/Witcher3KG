import json
import igraph as ig
from rdflib import Graph, URIRef, RDFS, RDF, Literal
from tqdm import tqdm
from llama_index.core import Document, VectorStoreIndex, StorageContext
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import os
import re

# Configurations
INPUT_KG = "../RDF/Witcher3KG_Relational.n3"
OUTPUT_DIR = "./witcher_index"
PASSAGES_FILE = os.path.join(OUTPUT_DIR, "lore_passages.jsonl")
GRAPH_FILE = os.path.join(OUTPUT_DIR, "topology.pkl")
ENTITY_MAP_FILE = os.path.join(OUTPUT_DIR, "entity_map.json")

embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-large-en-v1.5")

# Ontology Hubs to exclude from the GRAPH topology (prevents the system from over-connecting)
IGNORE_IN_GRAPH = [
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
    "http://cgi.di.uoa.gr/witcher/ontology#Humans",
    "http://www.w3.org/2002/07/owl#NamedIndividual",
    "http://www.w3.org/2002/07/owl#Class"
]

def get_name(kg, node):
    if isinstance(node, Literal): return str(node)
    label = kg.value(node, RDFS.label)
    if label: return str(label)
    return str(node).split('/')[-1].split('#')[-1].replace('_', ' ')

def build_hippo_indexes():
    print(f"[*] Loading KG: {INPUT_KG}...")
    kg = Graph()
    kg.parse(INPUT_KG, format="n3")
    
    all_uris = sorted(list(set(kg.subjects()) | {o for o in kg.objects() if isinstance(o, URIRef)}))
    uri_to_id = {str(uri): i for i, uri in enumerate(all_uris)}
    
    lore_passages = []
    nodes_for_vector = []

    print("[*] Generating Hierarchical Lore Passages...")
    for i, uri in enumerate(tqdm(all_uris)):
        name = get_name(kg, uri)
        
        # Categorize facts to prioritize narrative content
        relationships = []
        attributes = []
        classes = []

        for p, o in kg.predicate_objects(uri):
            p_uri = str(p)
            p_name = get_name(kg, p)
            o_name = get_name(kg, o)
            
            if p_uri == str(RDF.type):
                classes.append(o_name)
            elif isinstance(o, URIRef):
                relationships.append(f"The {p_name} of {name} is {o_name}")
            else:
                attributes.append(f"The {p_name} of {name} is {o_name}")

        # Construct the passage in order of importance
        text = f"LORE ENTRY FOR {name.upper()}.\n"
        if relationships: text += "RELATIONSHIPS: " + "; ".join(relationships) + ".\n"
        if attributes: text += "ATTRIBUTES: " + "; ".join(attributes) + ".\n"
        if classes: text += f"CLASSIFICATION: {name} belongs to the following categories: " + ", ".join(classes) + ".\n"

        lore_passages.append({"id": i, "name": name, "text": text})
        nodes_for_vector.append(Document(text=name, metadata={"uri": str(uri), "internal_id": i}))

    print("[*] Building Clean Topology (Relationships Only)...")
    edges = []
    for s, p, o in kg:
        if str(p) in IGNORE_IN_GRAPH: continue # Do not let energy flow through hubs
        if str(s) in uri_to_id and str(o) in uri_to_id:
            edges.append((uri_to_id[str(s)], uri_to_id[str(o)]))
    
    graph = ig.Graph(n=len(all_uris), edges=edges, directed=False)
    graph = graph.simplify()
    graph.write_pickle(GRAPH_FILE)

    print("[*] Saving...")
    VectorStoreIndex.from_documents(nodes_for_vector, embed_model=embed_model).storage_context.persist(persist_dir=os.path.join(OUTPUT_DIR, "vector_index"))
    with open(PASSAGES_FILE, 'w', encoding='utf-8') as f:
        for p in lore_passages: f.write(json.dumps(p) + "\n")
    with open(ENTITY_MAP_FILE, 'w') as f:
        json.dump({"to_id": uri_to_id}, f)
    print("[!] Done.")

if __name__ == "__main__": build_hippo_indexes()