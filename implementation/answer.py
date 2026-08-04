from sentence_transformers import CrossEncoder
from openai import OpenAI
from pydantic import BaseModel
from chromadb import PersistentClient
from litellm import completion
import gradio as gr 
from pathlib import Path



class Result(BaseModel):
    page_content: str
    metadata: dict

MODEL="ollama/llama3.2"
MODEL_ANS="ollama/llama3.1:8b"
collection_name="docs"
BASE_URL="http://localhost:11434/v1"
RETRIEVAL_K=8
openai= OpenAI(base_url=BASE_URL, api_key='llama')
reranker_model="BAAI/bge-reranker-v2-m3"
embedding_model ="qwen3-embedding:8b"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_NAME = PROJECT_ROOT / "vector_db"
chroma = PersistentClient(path=str(DB_NAME))
collection = chroma.get_or_create_collection(collection_name)



re_model=CrossEncoder(reranker_model)

def reranker(question, chunks, top_k=3):
    pairs=[(question, chunk.page_content) for chunk in chunks]
    scores=re_model.predict(pairs)
    ranked = sorted(
        zip(scores, chunks),
        key=lambda x: x[0],
        reverse=True
    )

    return [chunk for _, chunk in ranked[:top_k]]
    

def fetch_context_unranked(question):
    embedding=openai.embeddings.create(model=embedding_model, input=[question]).data[0].embedding
    results=collection.query(query_embeddings=embedding, n_results=RETRIEVAL_K)
    chunks=[]
    for result in zip(results["documents"][0], results["metadatas"][0]):
        chunks.append(Result(page_content=result[0], metadata=result[1]))
    return chunks        

def fetch_content(question):
    chunks=fetch_context_unranked(question)
    return reranker(question,chunks)


system_prompt="""You are an AI assistant specializing in disaster preparedness and emergency response.

<TASK>
Answer the user's question directly by synthesizing ONLY the provided context into a clean, well-organized response.
</TASK>

<DEFINITION_OF_SUCCESS>
You are successful ONLY when your response:
1. Hits Main Intent: Addresses the core question immediately (e.g., human emergency essentials first, with secondary topics like pets placed briefly at the end).
2. Strictly Grounded: Uses ONLY the provided context with zero external facts or outside memory.
3. Clear & Concise: Groups related items logically, eliminates duplicate points, and cuts non-essential fluff.
4. Direct Output: Starts directly with the answer—no introductory fluff ("First and foremost...") or meta-commentary.
</DEFINITION_OF_SUCCESS>

<CORE_RULES>
1. INTENT FOCUS & HIERARCHY:
   - Priority goes to the primary question. Secondary details in context (pets, vehicles, floods) must never overshadow the main answer.
2. ABSOLUTE GROUNDING:
   - Rely ONLY on facts explicitly stated in the RETRIEVED CONTEXT.
   - If information is missing, reply EXACTLY:
     "I don't have enough information in the provided documents to answer that."
3. FILTER & SYNTHESIZE:
   - Combine duplicate items into single points.
   - Omit low-priority or irrelevant filler.
</CORE_RULES>

<RETRIEVED_CONTEXT>
{context}
</RETRIEVED_CONTEXT>

Answer:"""

def make_rag_message(question, history, chunks):
    context='\n\n'.join(f"Extracted from {chunk.metadata["source"]}:\n{chunk.page_content}" for chunk in chunks)
    system_prompt_final=system_prompt.format(context=context)
    message=[{'role':'system','content':system_prompt_final}]+history+[{'role':'user','content':question}]
    return message 



def rewrite_query(question, history):
    message = f"""
You are a Query Rewriter for a Disaster Preparedness RAG system.

<TASK>
Rewrite the CURRENT USER QUESTION into a single, complete, standalone search query suitable for vector retrieval.
Use the CONVERSATION HISTORY only to resolve pronouns (e.g., "it", "they") or ambiguous follow-ups (e.g., "what else?", "what about for my dog?").
</TASK>

<RULES>
1. STANDALONE & SPECIFIC:
   - Make the query fully self-contained using context from the history if needed.
   - If the user's question is already complete and specific, keep it mostly as-is.

2. DO NOT ADD UNRELATED KEYWORDS:
   - Include specific disaster names or topic keywords ONLY if explicitly mentioned by the user or history.
   - Do NOT invent or add generic emergency terms that were not discussed.

3. CLEAN OUTPUT (CRUCIAL):
   - Output ONLY the raw search query text.
   - Do NOT add quotes, markdown formatting, explanations, or preambles (e.g., do NOT say "Rewritten query:").
   - Do NOT answer the question.
</RULES>

<CONVERSATION_HISTORY>
{history}
</CONVERSATION_HISTORY>

<CURRENT_QUESTION>
{question}
</CURRENT_QUESTION>

Standalone Search Query:
"""
    response=completion(model=MODEL, messages=[{'role':'system','content':message}])
    return response.choices[0].message.content


def answer_question(question: str, history: list[dict] = [])->tuple[str, list]:
    rewrite = rewrite_query(question, history).strip('"')
    chunks=fetch_content(rewrite)
    message=make_rag_message(question, history, chunks)
    response=completion(model=MODEL_ANS, messages=message, max_tokens=900, temperature=0.0)
    answer=response.choices[0].message.content
    return answer, chunks

def answer_gr(question: str, history: list[dict]= [])-> str:
    answer, _ =answer_question(question,history)
    return answer

async def answer_question_improved(question, history: list[dict] | None = None):
    from agents_coach.checker import evaluate_rag

    if history is None:
        history = []

    full_response = ""
    async for chunk in evaluate_rag(question, history):
        full_response += chunk
        yield full_response

if __name__=="__main__":
    gr.ChatInterface(fn=answer_question_improved).launch(inbrowser=True)
