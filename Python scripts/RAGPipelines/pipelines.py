# pipelines.py

import json
import argparse
import requests
from typing import Optional
from llama_index.core import load_index_from_storage, StorageContext, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import warnings
import re
from SPARQLWrapper import SPARQLWrapper, JSON

warnings.filterwarnings("ignore", category=FutureWarning, module="sentence_transformers.SentenceTransformer")

# --- SHARED SETUP ---

warnings.filterwarnings("ignore", category=FutureWarning, module="sentence_transformers.SentenceTransformer")

SPARQL_ENDPOINT_URL = "http://localhost:7200/repositories/da4dte_final"
NAMESPACES = """
    PREFIX witcher: <http://cgi.di.uoa.gr/witcher/ontology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX dbr: <http://cgi.di.uoa.gr/witcher/resource/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX geo: <http://www.opengis.net/ont/geosparql#>
    PREFIX geof: <http://www.opengis.net/def/function/geosparql/>
"""

print("--- Setting up LlamaIndex models ---")
Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-large-en-v1.5")
Settings.llm = None # We are using the DeepSeek API directly

print("--- Loading indexes from storage ---")
try:
    entity_index = load_index_from_storage(StorageContext.from_defaults(persist_dir="./storage/entity_index"))
    class_index = load_index_from_storage(StorageContext.from_defaults(persist_dir="./storage/class_index"))
    prop_index = load_index_from_storage(StorageContext.from_defaults(persist_dir="./storage/prop_index"))
except FileNotFoundError:
    raise FileNotFoundError("Error: Could not load indexes. Please run 'build_indexes.py' first.")

# Create a retriever for each index
entity_retriever = entity_index.as_retriever(similarity_top_k=5)
class_retriever = class_index.as_retriever(similarity_top_k=5)
prop_retriever = prop_index.as_retriever(similarity_top_k=5)

# --- TOOL DEFINITIONS (Python functions the agent can call) ---
def search_for_entity(query: str):
    """Searches the knowledge graph for specific named entities like people, places, or items."""
    nodes = entity_retriever.retrieve(query)
    return json.dumps([{"name": n.metadata['name'], "uri": n.metadata['uri']} for n in nodes])

def search_for_class(query: str):
    """Searches the knowledge graph for categories or types of things, like 'Witchers' or 'Cities'."""
    nodes = class_retriever.retrieve(query)
    return json.dumps([{"name": n.metadata['name'], "uri": n.metadata['uri']} for n in nodes])

def search_for_property(query: str):
    """Searches the knowledge graph for attributes or relationships, like 'hair color' or 'affiliations'."""
    nodes = prop_retriever.retrieve(query)
    return json.dumps([{"name": n.metadata['name'], "uri": n.metadata['uri']} for n in nodes])

# Define GeoSPARQL geospatial functions as context for the model
GEOSPATIAL_FUNCTIONS = [
    {
        "name": "sfWithin",
        "keywords": ["in", "inside", "within"],
        "description": "Used to find if a geometry is completely inside another geometry. Usage: FILTER(geof:sfWithin(?geomA, ?geomB))"
    },
    {
        "name": "sfIntersects",
        "keywords": ["crosses", "intersects", "goes through", "passes through"],
        "description": "Used to find if two geometries touch or overlap. Usage: FILTER(geof:sfIntersects(?geomA, ?geomB))"
    },
    {
        "name": "distance",
        "keywords": ["near", "close to", "nearby", "closest"],
        "description": "Used to calculate the distance between two geometries. Often used with ORDER BY. Usage: BIND(geof:distance(?geomA, ?geomB) AS ?distance)"
    }
]

def search_for_geospatial_function(query: str):
    """
    Searches for a relevant GeoSPARQL function based on keywords like 'inside', 'near', 'crosses'.
    """
    query_lower = query.lower()
    found_functions = []
    for func in GEOSPATIAL_FUNCTIONS:
        if any(keyword in query_lower for keyword in func['keywords']):
            found_functions.append({"name": func['name'], "description": func['description']})
    return json.dumps(found_functions)


# --- PIPELINE C: EXECUTION-GUIDED AGENT --

def execute_sparql_for_agent(query: str) -> str:
    """
    Executes a SPARQL query and returns a detailed JSON summary of the result,
    including the actual results if successful.
    """
    if not query or "ERROR" in query or "placeholder" in query.lower() or "[]" in query:
        return json.dumps({"status": "ERROR", "reason": "Invalid or placeholder query provided."})
    
    query_body = extract_sparql_from_llm_response(query)
    # Use a slightly higher limit for debugging queries
    query_with_limit = NAMESPACES + query_body + " LIMIT 5"
    
    sparql = SPARQLWrapper(SPARQL_ENDPOINT_URL)
    sparql.setQuery(query_with_limit)
    sparql.setReturnFormat(JSON)
    sparql.agent = "RAG-Agent-Tool/1.0"
    
    try:
        results = sparql.query().convert()
        if "boolean" in results:
            return json.dumps({"status": "SUCCESS", "boolean_result": results['boolean']})
        
        bindings = results["results"]["bindings"]
        if bindings:
            return json.dumps({
                "status": "SUCCESS",
                "rowCount": len(bindings),
                "results": bindings
            })
        else:
            return json.dumps({"status": "NO_RESULTS", "reason": "Query returned 0 results."})
    except Exception as e:
        return json.dumps({"status": "EXECUTION_ERROR", "reason": f"Query failed to execute: {e}"})
       
def find_equivalent_class(class_uri: str) -> str:
    """
    Finds classes that are equivalent to the given class_uri using the owl:sameAs property.
    This is useful for finding a geospatial map pin class that is linked to a conceptual class.
    """
    if not class_uri:
        return "Error: No class URI provided."
        
    query_body = f"SELECT ?equivalentClass WHERE {{ <{class_uri}> owl:sameAs ?equivalentClass . }}"
    sparql = SPARQLWrapper(SPARQL_ENDPOINT_URL)
    sparql.setQuery(NAMESPACES + query_body)
    sparql.setReturnFormat(JSON)
    sparql.agent = "RAG-Agent-Tool/1.0"
    try:
        results = sparql.query().convert()["results"]["bindings"]
        if results:
            equivalent_uris = [res['equivalentClass']['value'] for res in results]
            return json.dumps({"equivalent_classes": equivalent_uris})
        else:
            return "NO_EQUIVALENT_CLASSES_FOUND"
    except Exception:
        return "EXECUTION_ERROR: Failed to query for equivalent classes."

    
def extract_sparql_from_llm_response(text: str) -> str:
    """
    Intelligently extracts a SPARQL query from a larger block of text
    generated by an LLM.
    """
    if not text:
        return ""

    # First, remove markdown backticks if they exist
    cleaned_text = text.replace("```sparql", "").replace("```", "").strip()
    
    # Find the start of the query (SELECT or ASK), case-insensitive
    select_match = re.search(r'SELECT', cleaned_text, re.IGNORECASE)
    ask_match = re.search(r'ASK', cleaned_text, re.IGNORECASE)

    start_pos = -1
    if select_match:
        start_pos = select_match.start()
    elif ask_match:
        start_pos = ask_match.start()

    # If a keyword was found, return the substring from that point onwards
    if start_pos != -1:
        return cleaned_text[start_pos:].strip()
    
    # If no keyword is found, return the cleaned text as a last resort
    return cleaned_text


# --- PIPELINE A: SIMPLE RETRIEVE-AND-SYNTHESIZE ---

class SimpleRAGPipeline:
    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.deepseek.com/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.system_prompt = """
        You are an expert SPARQL/GeoSPARQL query generator. Your task is to convert a user's question into a valid SPARQL query for a Witcher 3 knowledge graph.
        You will be provided with the user's question and a context of potentially relevant entities, classes, and properties retrieved from the graph.
        Use the context to find the correct URIs and property names.
        Only output the final, complete SPARQL query. Do not include any explanations, markdown, or other text.
        """

    def generate_query(self, question: str) -> str:
        entity_nodes = entity_retriever.retrieve(question)
        class_nodes = class_retriever.retrieve(question)
        prop_nodes = prop_retriever.retrieve(question)

        context_str = "--- Retrieved Entities ---\n"
        for node in entity_nodes:
            context_str += f"- Name: {node.metadata['name']}, URI: <{node.metadata['uri']}>\n"
        
        context_str += "\n--- Retrieved Classes ---\n"
        for node in class_nodes:
            context_str += f"- Name: {node.metadata['name']}, URI: <{node.metadata['uri']}>\n"
            
        context_str += "\n--- Retrieved Properties ---\n"
        for node in prop_nodes:
            context_str += f"- Name: {node.metadata['name']}, URI: <{node.metadata['uri']}>\n"

        user_prompt = f"""
        User Question: "{question}"

        Retrieved Context:
        {context_str}

        Based on the question and the context, generate the SPARQL query.
        """
        
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 1024,
            "temperature": 0.1
        }
        
        response = requests.post(self.api_url, headers=self.headers, json=data)
        response.raise_for_status()
        result = response.json()
        raw_llm_output = result["choices"][0]["message"]["content"]
        return extract_sparql_from_llm_response(raw_llm_output)

# --- PIPELINE B: AGENTIC FUNCTION CALLING (GRASP-inspired) ---

class AgenticRAGPipeline:
    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.deepseek.com/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.available_tools = {
            "search_for_entity": search_for_entity,
            "search_for_class": search_for_class,
            "search_for_property": search_for_property,
            "search_for_geospatial_function": search_for_geospatial_function
        }
        self.system_prompt = """
        You are a reasoning agent that converts a user's question into a SPARQL/GeoSPARQL query.
        Your goal is to gather enough information to write the query.
        You have access to three tools to search a knowledge graph:
        1. search_for_entity(query): To find specific people, places, monsters, etc.
        2. search_for_class(query): To find types or categories of things.
        3. search_for_property(query): To find attributes or relationships.
        
        Follow this process:
        1. Analyze the user's question to identify the key entities, classes, and properties.
        2. Use the tools one by one to find the correct URIs for these components.
        3. After each tool call, review the results.
        4. Once you have gathered all necessary URIs, state that you are ready and then output the final, complete SPARQL query in a single block. Do not ask for permission.
        """
        self.tool_definitions = [
            {
                "type": "function",
                "function": {
                    "name": "search_for_entity",
                    "description": "Searches for specific named entities (people, places, items).",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "The name of the entity to search for, e.g., 'Geralt of Rivia'"}}, "required": ["query"]},
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_for_class",
                    "description": "Searches for a category or type of thing, e.g., 'Witcher', 'City'.",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "The name of the class to search for"}}, "required": ["query"]},
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_for_property",
                    "description": "Searches for an attribute or relationship, e.g., 'hair color', 'location'.",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "The name of the property to search for"}}, "required": ["query"]},
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_for_geospatial_function",
                    "description": "Finds the correct GeoSPARQL function for spatial queries.",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "A spatial keyword, e.g., 'inside', 'near', 'crosses'"}}, "required": ["query"]},
                }
            }
        ]

    def generate_query(self, question: str, max_steps: int = 10) -> str:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": question}
        ]
        
        for _ in range(max_steps):
            data = {
                "model": self.model,
                "messages": messages,
                "tools": self.tool_definitions,
                "tool_choice": "auto"
            }
            
            response = requests.post(self.api_url, headers=self.headers, json=data)
            response.raise_for_status()
            result = response.json()
            response_message = result["choices"][0]["message"]
            
            # Append the assistant's entire message (which may include tool calls) to the history
            messages.append(response_message)
            
            if response_message.get("tool_calls"):
                for tool_call in response_message["tool_calls"]:
                    function_name = tool_call['function']['name']
                    function_args = json.loads(tool_call['function']['arguments'])
                    
                    # Call the actual Python function
                    function_response = self.available_tools[function_name](query=function_args.get("query"))
                    
                    # Append the tool's response in the correct format for the next API call
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call['id'],
                        "content": function_response,
                    })
            else:
                # If there are no tool calls, the model has given its final text answer
                final_content = response_message.get('content')
                if final_content and ("SELECT" in final_content or "ASK" in final_content):
                    return extract_sparql_from_llm_response(final_content)
                # If it's just a thought, the loop will continue with the updated message history
        
        # Fallback if the loop finishes without generating a query
        messages.append({"role": "user", "content": "You have now gathered all the information. Please generate the final SPARQL query based on our conversation."})
        final_data = {"model": self.model, "messages": messages}
        final_response = requests.post(self.api_url, headers=self.headers, json=final_data)
        final_response.raise_for_status()
        final_result = final_response.json()
        final_query_raw = final_result["choices"][0]["message"]["content"]
        return extract_sparql_from_llm_response(final_query_raw)
    
class ExecutionGuidedAgent:
    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.deepseek.com/chat/completions"
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self.available_tools = {
            "search_for_entity": search_for_entity,
            "search_for_class": search_for_class,
            "search_for_property": search_for_property,
            "search_for_geospatial_function": search_for_geospatial_function,
            "execute_sparql_query": execute_sparql_for_agent,
            "find_equivalent_class": find_equivalent_class
        }
        self.system_prompt = """
        You are a highly advanced reasoning agent that converts a user's question into a perfect SPARQL query.
        The graph contains detailed information about characters, locations, items from the witcher wiki and geospatial data (polygons) for the witcher 3 "Novigrad and Velen Map" as well as all the map pins in the games (POIs).
        
        **Your Goal:** Generate a single, executable SPARQL query that correctly answers the user's question.

        **CRITICAL SPARQL RULES:**
        1.  **Names:** Always use `rdfs:label` to get human-readable names.
        2.  **Geospatial:** Use `geo:hasGeometry/geo:asWKT` to get geometry strings from named entities (like `dbr:Novigrad`).
        3.  **Prefixes:** Declare and use `witcher:`, `dbr:`, `rdfs:`, `geo:`, `geof:`.
        4.  **Yes/No Questions:** For yes/no questions, make sure to only return "Yes" or "No" in the final answer.
        5.  **Conceptual to Geospatial Class Mapping:** If a geospatial query fails due to a conceptual class (e.g., `witcher:Blacksmiths`), use the `find_equivalent_class` tool to find a geospatially relevant class (e.g., `witcher:Blacksmith`) and retry your query. This works for many Mappin/POI types like quests etc. as well as the map entities like Novigrad/Velen Map. Usually plural is used for the conceptual class and singular for the geospatial one.
        6.  To find out which map a location is on, you can use the property `witcher:isPartOf` but prefer geospatial reasoning over this.
        7.  The only map with geospatial data is the dbr:Velen_Novigrad_Map. Other maps with similar names are conceptual and do not have polygons but are connected through the owl:sameAs property.
        8.  **Comparative Queries:** For comparative queries (e.g., "Does A have more items than B?"), ensure your query retrieves the necessary attributes for both entities and includes logic to compare them, returning "yes" or "no" as appropriate. 
        9.  **String Matching:** You MUST NOT use `FILTER(CONTAINS(...))` for string matching. Always use exact matches with URIs or `rdfs:label`. Only use it as a last resort or when searching for classes/properties/entities.
        10. **Location Queries:** For queries about locations, always try to use geospatial reasoning (e.g., `geof:sfWithin`, `geof:sfIntersects`, `geof:distance`) instead of relying solely on properties like witcher:location. Properties like witcher:location, witcher:region and witcher:isPartOf should only be used as a last resort.
        11. **Instance Listing:** When a question asks to list all things of a specific kind, look for the class using the `search_for_class` tool and then list all instances of that class with their labels.

        **Your Reasoning Process (Chain-of-Thought):**

        **Step 1: Decompose and Find Candidates.**
        Break down the user's question. If it is a comparative question, identify the two locations and the item type being compared. Use your search tools to find candidate URIs for each component.

        **Step 2: Formulate a Hypothesis.**
        Create a  SPARQL query skeleton and use the top candidate for each component, following the CRITICAL RULES.

        **Step 3: Test and Verify.**
        Use your `execute_sparql_query` tool with your hypothesis query.

        **Step 4: Analyze and Self-Correct.**
        Analyze the JSON response from the `execute_sparql_query` tool:
        - If the `"status"` is **'SUCCESS'**: You are done. Proceed to the final step.
        - If the `"status"` is **'NO_RESULTS'**: Your query failed, likely due to an incorrect class URI.
            - **Action 1 (Primary Recovery):** Call the `find_equivalent_class` tool with the class URI that just failed. If it returns a new URI, your IMMEDIATE next action is to formulate a new hypothesis using this new URI and test it with `execute_sparql_query`.
            - **Action 2 (Last Resort Debugging):** If `find_equivalent_class` fails, run a debugging query to discover new class URIs, for example: `SELECT DISTINCT ?class WHERE {{ ?s a ?class . FILTER(CONTAINS(LCASE(STR(?class)), "keyword")) }}`.
            - **Action 3 (Crucial):** After running a debugging query that returns a 'SUCCESS' status, you MUST **inspect the `results` field** in the JSON response. Extract a relevant URI from the results and use it to build your final hypothesis. Test this final hypothesis with `execute_sparql_query`.
        - If the `"status"` is **'EXECUTION_ERROR'**: Your query has a syntax error. Fix it and try again.

        **Step 5: Final Output.**
        Once `execute_sparql_query` returns a 'SUCCESS' status, output that validated query as your final answer. Do not include any other text.
        In case the maximum number of reasoning steps is reached, output the best SPARQL query you have so far, even if it hasn't been validated.
        Under no circumstances should you output anything other than the final SPARQL query.
        """
        self.tool_definitions = [
            {
                "type": "function",
                "function": {
                    "name": "search_for_entity",
                    "description": "Searches for specific named entities (people, places, items).",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "The name of the entity to search for, e.g., 'Geralt of Rivia'"}}, "required": ["query"]},
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_for_class",
                    "description": "Searches for a category or type of thing, e.g., 'Witcher', 'City'.",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "The name of the class to search for"}}, "required": ["query"]},
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_for_property",
                    "description": "Searches for an attribute or relationship, e.g., 'hair color', 'location'.",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "The name of the property to search for"}}, "required": ["query"]},
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_for_geospatial_function",
                    "description": "Finds the correct GeoSPARQL function for spatial queries.",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "A spatial keyword, e.g., 'inside', 'near', 'crosses'"}}, "required": ["query"]},
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_sparql_query",
                    "description": "Executes a complete SPARQL query and returns a summary of the result (SUCCESS, NO_RESULTS, or ERROR). Use this to test and disambiguate URI candidates.",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "The full SPARQL query to execute."}}, "required": ["query"]},
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "find_equivalent_class",
                    "description": "Given a class URI, finds other classes linked by owl:sameAs. Use this to find a geospatial class from a conceptual one.",
                    "parameters": {"type": "object", "properties": {"class_uri": {"type": "string", "description": "The URI of the class that failed in a query."}}, "required": ["class_uri"]},
                }
            }
        ]

    def generate_query(self, question: str, max_steps: int = 20) -> str:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": question}
        ]
        
        final_query_raw = ""

        for step in range(max_steps):
            data = {
                "model": self.model,
                "messages": messages,
                "tools": self.tool_definitions,
                "tool_choice": "auto"
            }

            try:
                response = requests.post(self.api_url, headers=self.headers, json=data)
                response.raise_for_status()
                result = response.json()
                response_message = result["choices"][0]["message"]
            except Exception as e:
                return f"ERROR: API call failed at step {step + 1}: {e}"

            messages.append(response_message)

            if response_message.get("tool_calls"):
                for tool_call in response_message["tool_calls"]:
                    function_name = tool_call['function']['name']
                    function_args = json.loads(tool_call['function']['arguments'])
                    
                    try:
                        if function_name == 'find_equivalent_class':
                            function_response = self.available_tools[function_name](class_uri=function_args.get("class_uri"))
                        else:
                            function_response = self.available_tools[function_name](query=function_args.get("query"))
                    except Exception as e:
                        function_response = f"Error executing tool: {e}"
                        
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call['id'],
                        "content": function_response,
                    })
            else:
                final_content = response_message.get('content', '')
                if "SELECT" in final_content.upper() or "ASK" in final_content.upper():
                    final_query_raw = final_content
                    break

        if not final_query_raw:
            # Fallback for max steps
            messages.append({"role": "user", "content": "You have now gathered all the information. Please generate the final SPARQL query based on our conversation."})
            final_data = {"model": self.model, "messages": messages}
            final_response = requests.post(self.api_url, headers=self.headers, json=final_data)
            final_response.raise_for_status()
            final_result = final_response.json()
            final_query_raw = final_result["choices"][0]["message"]["content"]
        
        return extract_sparql_from_llm_response(final_query_raw)