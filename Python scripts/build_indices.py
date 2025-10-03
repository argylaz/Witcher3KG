# build_indices.py
import warnings
from llama_index.core import VectorStoreIndex, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

# Import your new, enriched data preparation function
from prepare_data import extract_and_format_enriched_data

# Suppress a harmless warning from the sentence-transformers library
warnings.filterwarnings("ignore", category=FutureWarning, module="sentence_transformers.SentenceTransformer")

def build_and_persist_indexes():
    """Builds and saves the three specialized indexes from the enriched data."""
    
    print("--- Setting up LlamaIndex embedding model ---")
    # For indexing, we ONLY need the embedding model. This is efficient.
    try:
        Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-large-en-v1.5")
    except Exception as e:
        print(f"Error initializing embedding model. Is sentence-transformers installed? Error: {e}")
        return
    
    # We explicitly set the LLM to None for this script.
    Settings.llm = None
    print("LLM is not required for indexing. Proceeding with embedding model only.")

    # 1. Get the enriched data
    entity_docs, class_docs, prop_docs = extract_and_format_enriched_data()

    # 2. Build and persist the ENTITY index
    print("\n--- Building Enriched Entity Index ---")
    entity_index = VectorStoreIndex.from_documents(entity_docs, show_progress=True)
    entity_index.storage_context.persist(persist_dir="./storage/entity_index")
    print("Entity Index built and saved to ./storage/entity_index")

    # 3. Build and persist the CLASS index
    print("\n--- Building Class Index ---")
    class_index = VectorStoreIndex.from_documents(class_docs, show_progress=True)
    class_index.storage_context.persist(persist_dir="./storage/class_index")
    print("Class Index built and saved to ./storage/class_index")

    # 4. Build and persist the PROPERTY index
    print("\n--- Building Property Index ---")
    prop_index = VectorStoreIndex.from_documents(prop_docs, show_progress=True)
    prop_index.storage_context.persist(persist_dir="./storage/prop_index")
    print("Property Index built and saved to ./storage/prop_index")

if __name__ == "__main__":
    build_and_persist_indexes()