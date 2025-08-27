import requests
import json
import argparse
from typing import Optional

class SPARQLTranslator:
    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        """
        Initialize the SPARQL translator with DeepSeek API credentials
        
        Args:
            api_key: Your DeepSeek API key
            model: The DeepSeek model to use ("deepseek-chat" or "deepseek-reasoner")
        """
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.deepseek.com/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def translate_query(self, sparql_query: str, context: Optional[str] = None) -> str:
        """
        Translate a SPARQL query to natural language using DeepSeek API
        
        Args:
            sparql_query: The SPARQL query to translate
            context: Optional context about the dataset or domain
            
        Returns:
            Natural language translation of the query
        """
        # Construct the prompt
        system_prompt = """You are an expert SPARQL-to-natural language translator. 
        Convert the given SPARQL query into a clear, concise, and accurate natural language question.
        Focus on maintaining the semantic meaning while making it easily understandable. Only return the natural language question"""
        
        user_prompt = f"Translate this SPARQL query to natural language:"
        if context:
            user_prompt += f"\nContext: {context}"
        user_prompt += f"\n\nSPARQL Query:\n{sparql_query}"
        
        # Prepare the API request
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,  # Lower temperature for more precise translations
            "max_tokens": 500,
            "stream": False
        }
        
        try:
            # Make the API request
            response = requests.post(self.api_url, headers=self.headers, json=data)
            response.raise_for_status()
            
            # Extract and return the translation
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"API request failed: {str(e)}")
        except (KeyError, IndexError) as e:
            raise Exception(f"Failed to parse API response: {str(e)}")

def main():
    # Set up command line arguments
    parser = argparse.ArgumentParser(description="Translate SPARQL queries to natural language using DeepSeek API")
    parser.add_argument("--api-key", required=True, help="Your DeepSeek API key")
    parser.add_argument("--query", required=True, help="SPARQL query to translate")
    parser.add_argument("--context", help="Additional context about the dataset or domain")
    parser.add_argument("--model", default="deepseek-chat", 
                       choices=["deepseek-chat", "deepseek-reasoner"],
                       help="DeepSeek model to use")
    parser.add_argument("--output", help="Output file to save results (optional)")
    
    args = parser.parse_args()
    
    # Initialize the translator
    translator = SPARQLTranslator(args.api_key, args.model)
    
    # Translate the query
    try:
        natural_language_query = translator.translate_query(args.query, args.context)
        
        # Print and optionally save the result
        print("Natural Language Translation:")
        print(natural_language_query)
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(natural_language_query)
            print(f"\nResult saved to {args.output}")
            
    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()