import requests
import json
import os
from datetime import datetime

# Configuration
API_URL = "http://localhost:8000/api/ask"
OUTPUT_FILE = "evaluation_report.md"

# Test Questions
QUESTIONS = [
    "What are the duties of a director?",
    "What is the penalty for fraud?",
    "How is an independent director appointed?",
    "Can a company buy back its own shares?",
    "What are the requirements for a board meeting quorum?"
]

def get_answer(question, use_rag):
    try:
        response = requests.post(
            API_URL, 
            json={"question": question, "use_rag": use_rag},
            stream=True
        )
        response.raise_for_status()
        
        full_answer = ""
        sources = []
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data_str = line[6:]
                    if data_str == '[DONE]':
                        break
                    try:
                        data = json.loads(data_str)
                        if 'content' in data:
                            full_answer += data['content']
                        if 'sources' in data:
                            sources = data['sources']
                    except:
                        pass
                        
        return full_answer, sources
    except Exception as e:
        return f"Error: {str(e)}", []

def run_evaluation():
    print(f"Starting evaluation on {len(QUESTIONS)} questions...")
    
    with open(OUTPUT_FILE, "w") as f:
        f.write(f"# LegalGPT RAG Evaluation Report\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        for i, q in enumerate(QUESTIONS):
            print(f"Processing Q{i+1}: {q}")
            
            # Non-RAG
            print("  - Fetching Non-RAG response...")
            ans_no_rag, _ = get_answer(q, use_rag=False)
            
            # RAG
            print("  - Fetching RAG response...")
            ans_rag, sources = get_answer(q, use_rag=True)
            
            # Write to file
            f.write(f"## Question {i+1}: {q}\n\n")
            
            f.write("### ❌ Without RAG\n")
            f.write(f"{ans_no_rag}\n\n")
            
            f.write("### ✅ With RAG\n")
            f.write(f"{ans_rag}\n\n")
            
            if sources:
                f.write("**Sources:**\n")
                for s in sources:
                    f.write(f"- {s.get('title', 'Unknown')} ({s.get('url', 'Unknown')})\n")
            else:
                f.write("**Sources:** None\n")
                
            f.write("\n---\n\n")
            
    print(f"Evaluation complete! Report saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    run_evaluation()
