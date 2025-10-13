# test_single_query.py

import json
import argparse
import requests
from typing import Optional

# Import the main pipeline class, which now works with requests
from pipelines import SimpleRAGPipeline, AgenticRAGPipeline, extract_sparql_from_llm_response
from pipelines import search_for_entity, search_for_class, search_for_property

# --- A VERBOSE VERSION OF THE AGENTIC PIPELINE (using requests) ---
class VerboseAgenticRAGPipeline:
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
            "search_for_property": search_for_property
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
            }
        ]

    def generate_query_and_log(self, question: str, max_steps: int = 5) -> (str, str):
        log_entries = []
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": question}
        ]
        
        log_entries.append("--- Agent Conversation Log ---")
        log_entries.append(f"USER: {question}")
        
        final_query_raw = ""
        
        print("\n--- Agent Conversation Log ---")
        print(f"USER: {question}")
        
        for step in range(max_steps):
            print(f"\n--- Step {step + 1}: Sending conversation to API ---")
            
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

            # Append the raw assistant message dictionary to our history
            messages.append(response_message)

            if response_message.get("tool_calls"):
                print("ASSISTANT (Decision): The model decided to call a tool.")
                print(f"  -> Raw Tool Calls: {response_message['tool_calls']}")
                
                for tool_call in response_message["tool_calls"]:
                    function_name = tool_call['function']['name']
                    function_args = json.loads(tool_call['function']['arguments'])
                    query_arg = function_args.get("query")
                    
                    print(f"  -> Executing tool: {function_name}(query='{query_arg}')")
                    function_response = self.available_tools[function_name](query=query_arg)
                    print(f"TOOL RESPONSE: {function_response}")
                    
                    # Append the tool's response for the next turn
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call['id'],
                        "content": function_response,
                    })
            else:
                final_content = response_message.get('content', '')
                log_entries.append(f"ASSISTANT (Final Answer/Thought):\n{final_content}")
                if "SELECT" in final_content.upper() or "ASK" in final_content.upper():
                    final_query_raw = final_content
                    # We found the query, so we can exit the loop
                    break

        # Fallback if loop finishes
        if not final_query_raw:
            log_entries.append("\n--- Max steps reached, forcing final generation ---")
            messages.append({"role": "user", "content": "You have now gathered all the information. Please generate the final SPARQL query based on our conversation."})
            final_data = {"model": self.model, "messages": messages}
            final_response = requests.post(self.api_url, headers=self.headers, json=final_data)
            final_response.raise_for_status()
            final_result = final_response.json()
            final_query_raw = final_result["choices"][0]["message"]["content"]
            log_entries.append(f"ASSISTANT (Forced Final Answer):\n{final_query_raw}")
        
        # Use the robust parser on the final raw output
        clean_sparql = extract_sparql_from_llm_response(final_query_raw)
        return clean_sparql, "\n".join(log_entries)


def main():
    parser = argparse.ArgumentParser(description="Test and debug the RAG-to-SPARQL pipelines with a single query.")
    parser.add_argument("--api-key", required=True, help="Your DeepSeek API key.")
    parser.add_argument("question", type=str, help="The natural language question to test, enclosed in quotes.")
    parser.add_argument("--log-file", help="Optional file to save the verbose agent conversation log.")
    args = parser.parse_args()

    # --- 1. Test Pipeline A (Simple RAG) ---
    # print("="*20, "Testing Pipeline A (Simple RAG)", "="*20)
    # pipeline_a = SimpleRAGPipeline(api_key=args.api_key)
    # try:
    #     generated_sparql_a = pipeline_a.generate_query(args.question)
    #     print("\n--- Pipeline A Generated SPARQL ---")
    #     print(generated_sparql_a)
    # except Exception as e:
    #     print(f"\n--- Pipeline A Failed ---")
    #     print(f"Error: {e}")

    # --- 2. Test Pipeline B (Agentic RAG) ---
    print("\n\n" + "="*20, "Testing Pipeline B (Agentic RAG)", "="*20)
    pipeline_b = VerboseAgenticRAGPipeline(api_key=args.api_key)
    try:
        # Unpack the two return values
        generated_sparql_b, conversation_log = pipeline_b.generate_query_and_log(args.question)
        
        # Print the log to the console for immediate feedback
        print(conversation_log)
        
        print("\n--- Pipeline B Generated SPARQL ---")
        print(generated_sparql_b)

        # If a log file was specified, save the output
        if args.log_file:
            with open(args.log_file, 'w') as f:
                f.write(conversation_log)
                f.write("\n\n" + "="*20 + " Final Generated SPARQL " + "="*20 + "\n")
                f.write(generated_sparql_b)
            print(f"\n[+] Conversation log saved to '{args.log_file}'")

    except Exception as e:
        print(f"\n--- Pipeline B Failed ---")
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
