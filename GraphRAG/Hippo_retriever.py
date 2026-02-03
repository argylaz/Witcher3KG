import json
import igraph as ig
import os
import time
import requests
import numpy as np
from llama_index.core import StorageContext, load_index_from_storage
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

# --- CONFIGURATION ---
OPENROUTER_API_KEY = "" #"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" 
MODEL_NAME = "meta-llama/llama-3.3-70b-instruct:free"

# Paths - Ensure these match your local Windows directory structure
BASE_PATH = r"C:\Users\argyl\Downloads\D.I.T\Πτυχιακη\Witcher3KG\GraphRAG\witcher_index"
# BASE_PATH = r"C:\Users\argyl\Downloads\D.I.T\Πτυχιακη\Witcher3KG\GraphRAG\witcher_wiki_index" # USE FOR WIKI TEXT
VECTOR_DIR = os.path.join(BASE_PATH, "vector_index")
GRAPH_FILE = os.path.join(BASE_PATH, "topology.pkl")
MAP_FILE = os.path.join(BASE_PATH, "entity_map.json")
LORE_FILE = os.path.join(BASE_PATH, "lore_passages.jsonl")

# Initialize Embedding Model (large to match thesis indexx dimensions)
embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-large-en-v1.5")


class WitcherHippoRetriever:
    def __init__(self):
        print("[*] Initializing HippoRAG Multi-Index...")
        
        # Load Thesis Vector Index (The Entry Point Finder)
        print(f"    -> Loading Vector Index...")
        storage_context = StorageContext.from_defaults(persist_dir=VECTOR_DIR)
        self.vector_index = load_index_from_storage(storage_context, embed_model=embed_model)
        
        # Load Graph Topology (The Hippocampus)
        print(f"    -> Loading Graph Topology...")
        self.graph = ig.Graph.Read_Pickle(GRAPH_FILE)
        
        # Load Mapping (URI -> ID)
        with open(MAP_FILE, 'r') as f:
            self.uri_to_id = json.load(f)['to_id']
        
        # Load Text Passages
        print(f"    -> Loading Lore Passages...")
        self.passages = {}
        with open(LORE_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                item = json.loads(line)
                self.passages[str(item['id'])] = item
        
        print("[+] All systems ready.\n")

    def retrieve_context(self, query, top_k_entities=3, top_n_passages=10):
        print(f"[*] Querying: {query}")

        # Vector Search
        retriever = self.vector_index.as_retriever(similarity_top_k=top_k_entities)
        nodes = retriever.retrieve(query)
        seed_ids = [self.uri_to_id.get(n.metadata['uri']) for n in nodes if self.uri_to_id.get(n.metadata['uri']) is not None]
        
        if not seed_ids: return None

        # Spreading Activation
        num_nodes = self.graph.vcount()
        scores = np.zeros(num_nodes)
        for sid in seed_ids: scores[sid] = 1.0
        
        # 3-step hop to ensure we cross through complex relationships
        for _ in range(3):
            new_scores = np.zeros(num_nodes)
            for i in range(num_nodes):
                if scores[i] > 0:
                    neighbors = self.graph.neighbors(i)
                    if neighbors:
                        # Spread activation, slightly decay each hop (0.7) 
                        amt = (scores[i] * 0.7) / len(neighbors)
                        for nb in neighbors: new_scores[nb] += amt
            scores += new_scores

        # Assembly
        top_indices = np.argsort(scores)[::-1][:top_n_passages]
        print("\n--- Top Retrieved Entities ---")
        context = []
        for idx in top_indices:
            p = self.passages[str(idx)]
            print(f"Node: {p['name']} | Score: {scores[idx]:.4f}")
            context.append(p['text'])
        
        return "\n\n".join(context)

    def generate_answer(self, query, context, max_retries=3):
        """Direct HTTP implementation for OpenRouter models."""
        prompt = f"Use the Witcher lore passages to answer the question briefly. If the answer is not in the lore, say you don't know.\n\nLORE:\n{context}\n\nQUESTION: {query}\nANSWER:"
        
        for attempt in range(max_retries):
            try:
                headers = {
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost/WitcherKG",
                    "X-Title": "Witcher3-GraphRAG-Project",
                }
                data_payload = {
                    "model": MODEL_NAME,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 512,
                    "stream": False,
                    "temperature": 0.1
                }

                response = requests.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    data=json.dumps(data_payload),
                    timeout=60
                )

                response.raise_for_status() 
                result = response.json()
                return result['choices'][0]['message']['content'].strip()
                
            except Exception as e:
                print(f"  - LLM Attempt {attempt+1} failed: {e}")
                time.sleep(2 * (attempt + 1))
        
        return "ERROR: Could not reach LLM."

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    hippo = WitcherHippoRetriever()
    
    # Example question that tests multi-hop graph retrieval
    test_q = "Who is the child of Pavetta and what is her hair color?"
    
    lore = hippo.retrieve_context(test_q)
    
    if lore:
        print("\n[*] Graph context retrieved. Generating answer...")
        answer = hippo.generate_answer(test_q, lore)
        print(f"\n[QWEN ANSWER]:\n{answer}")
    else:
        print("\n[!] No context found in graph.")