from sentence_transformers import CrossEncoder
from openai import OpenAI
from pydantic import BaseModel
from chromadb import PersistentClient
from litellm import completion
import gradio as gr 



class Result(BaseModel):
    page_content: str
    metadata: dict

MODEL="ollama/llama3.2"
collection_name="docs"
DB_name="vector_db"
BASE_URL="http://localhost:11434/v1"
RETRIEVAL_K=6
openai= OpenAI(base_url=BASE_URL, api_key='llama')
reranker_model="BAAI/bge-reranker-v2-m3"
embedding_model = "qwen3-embedding:4b"
chroma = PersistentClient(path=DB_name)
collection = chroma.get_or_create_collection(collection_name)



re_model=CrossEncoder(reranker_model)
def reranker(question, chunks):
    pairs=[(question, chunk.page_content) for chunk in chunks]
    scores=re_model.predict(pairs)
    ranked_chunks= [chunk for _,chunk in sorted(zip(scores,chunks), reverse=True)]
    return ranked_chunks
    

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



system_prompt = """
You are an AI assistant specializing in disaster preparedness and emergency response.

Your task is to answer the user's question using ONLY the information provided below.

Retrieved Context:
{context}

Instructions:

1. Use ONLY the retrieved information. Never use outside knowledge or assumptions.
2. If the retrieved information does not contain enough information to answer the question, respond exactly:
   "I don't have enough information in the provided documents to answer that."
3. Carefully read ALL retrieved passages before answering.
4. Combine relevant information from every retrieved passage into one complete answer.
5. Do NOT ignore information simply because it appears in a later passage.
6. If multiple passages provide different pieces of the answer, include ALL of them.
7. Do not repeat the same information.
8. Present safety instructions, recommendations, precautions, preparation steps, recovery steps, or checklists as a numbered list.
9. When the retrieved information contains several recommendations, include every important recommendation instead of selecting only a few.
10. Keep the answer factual and well organized, but prioritize completeness over brevity.
11. Use natural, easy-to-understand language.
12. Do not mention retrieved documents, context, sources, or the retrieval process.
13. Do not invent, infer, or add information that is not explicitly supported.
14. If the retrieved information contains warnings, exceptions, or conditions, include them in the answer.
15. If the user asks "how", "what should I do", "how can I prepare", or similar procedural questions, provide every relevant step in logical order.

Answer:
"""

def make_rag_message(question, history, chunks):
    context='\n\n'.join(f"Extracted from {chunk.metadata["source"]}:\n{chunk.page_content}" for chunk in chunks)
    system_prompt_final=system_prompt.format(context=context)
    message=[{'role':'system','content':system_prompt_final}]+history+[{'role':'user','content':question}]
    return message 



def rewrite_query(question, history):
    message = f"""
You are assisting a Retrieval-Augmented Generation (RAG) system for disaster preparedness.

Your task is to rewrite the user's question into a short, specific search query that will retrieve the most relevant documents from the knowledge base.

Conversation history:
{history}

Current user question:
{question}

Instructions:
- Produce a concise search query (5 to 15 words if possible).
- Preserve the user's intent and important details.
- Include relevant disaster names, emergency situations, or preparedness topics (e.g., flood, wildfire, evacuation, emergency kit, pets, caregivers).
- If the current question depends on the conversation history (for example, "What should I do next?"), rewrite it into a complete standalone query.
- Do not answer the question.
- Do not add explanations or formatting.
- Respond with ONLY the search query.
"""
    response=completion(model=MODEL, messages=[{'role':'system','content':message}])
    return response.choices[0].message.content


def answer_question(question: str, history: list[dict] = [])->tuple[str, list]:
    rewrite = rewrite_query(question, history).strip('"')
    chunks=fetch_content(rewrite)
    message=make_rag_message(question, history, chunks)
    response=completion(model=MODEL, messages=message, max_tokens=768)
    answer=response.choices[0].message.content
    return answer, chunks

def answer_gr(question: str, history: list[dict]= [])-> str:
    answer, _ =answer_question(question,history)
    return answer

if __name__=="__main__":
    gr.ChatInterface(fn=answer_gr).launch(inbrowser=True)
