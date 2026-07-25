
import glob
from pydantic import BaseModel, Field
from chromadb import PersistentClient
import json
from tqdm import tqdm
from openai import OpenAI
from chonkie import TokenChunker
from dotenv import load_dotenv
import os
from multiprocessing import Pool
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_NAME = PROJECT_ROOT / "vector_db"
chroma = PersistentClient(path=str(DB_NAME))


load_dotenv()
api_key = os.getenv("HF_TOKEN")



class Result(BaseModel):
    page_content: str
    metadata: dict


MODEL='ollama/llama3.2'
embedding_model ="qwen3-embedding:4b"
collection_name="docs"
RETRIEVAL_K=6
DB_name="vector_db"
BASE_URL="http://localhost:11434/v1"
openai= OpenAI(base_url=BASE_URL, api_key='llama')
reranker_model="BAAI/bge-reranker-v2-m3"


def fetch_documents():
    documents=[]
    for file in glob.glob(r"D:\disaster\Disaster-Management-RAG\knowledge_base/*"):
        with open(file, 'r', encoding='utf-8') as f:
            doc=json.load(f)
            if not doc["text"]==None:
                doc['title']=doc['title'].split('|')[0].strip()
                documents.append(doc)   
    print(f"Loaded {len(documents)} documents.")            
    return documents                     




chunker = TokenChunker(chunk_size=512, chunk_overlap=128) #overlaping=25%


def process_document(doc):
    chunked = chunker.chunk(doc["text"])

    return [
        Result(
            page_content=f"Type: {doc['title']}\n\n{chunk}",
            metadata={
                "type": doc["title"],
                "source": doc["source"],
            },
        )
        for chunk in chunked
    ]


def create_Chunks(documents, workers=5):
    with Pool(processes=workers) as pool:
        results = list(
            tqdm(
                pool.imap(process_document, documents),
                total=len(documents),
            )
        )

    chunks = []
    for result in results:
        chunks.extend(result)

    return chunks



def create_embeddings(chunks):
    vectors=[]
    if collection_name in [c.name for c in chroma.list_collections()]:
        chroma.delete_collection(collection_name)
    text=[chunk.page_content for chunk in chunks]
    ids=[str(i) for i in range(len(chunks))] 
    metas=[chunk.metadata for chunk in chunks] 
    for t in tqdm(text):
        emb=openai.embeddings.create(model=embedding_model, input=t).data
        vectors.append(emb[0].embedding)  
    collection=chroma.get_or_create_collection(collection_name)
    collection.add(ids=ids, embeddings=vectors, documents=text, metadatas=metas)
    print(f"Vectorstore created with {collection.count()} documents")



if __name__=="__main__":
    documents=fetch_documents()
    chunks=create_Chunks(documents, workers=5)
    create_embeddings(chunks)
    print("Ingestion complete!")
