import sys
from pathlib import Path

project_root = Path.cwd().parent
sys.path.insert(0, str(project_root))

from implementation.answer import answer_question
from agents import Agent, Runner, SQLiteSession, OpenAIChatCompletionsModel, set_tracing_disabled
from openai import AsyncOpenAI
import json
from pydantic import BaseModel, Field
import asyncio
from tqdm import tqdm
import os
import requests
import asyncio
from .prompts import accuracy_instruction, completeness_instruction, rewrite_instruction, relevance_instruction


pushover_user = os.getenv("PUSHOVER_USER")
pushover_token = os.getenv("PUSHOVER_TOKEN")
pushover_url = "https://api.pushover.net/1/messages.json"
model="llama3.1"
iteration=5
base_url = "http://localhost:11434/v1"
set_tracing_disabled(True)



class Scoring(BaseModel):
    score: float = Field(description="Score from 0 to 5, in increments of 0.5")
    diagnosis: str = Field(description="1-2 sentences: what specific fact is wrong, and what the reference actually says")
    fix_instruction: str = Field(description="1-2 sentences, imperative, telling the next answer exactly what to correct")


class ImprovementRecord(BaseModel):
    iteration:int 
    average_score: float
    current_answer: str


class Memory():
    def __init__(self):
        self.history: list[ImprovementRecord] = [] 
        

    def add(self,iteration:int,average_score: float, current_answer: str):
        self.history.append(
             ImprovementRecord(
                iteration=iteration,
                current_answer=current_answer,
                average_score=average_score
             )
        )


ollama_client=AsyncOpenAI(base_url=base_url, api_key="llama")
llama_model=OpenAIChatCompletionsModel(model=model, openai_client=ollama_client)

def query_form(question,reference_answer,candidate_answer):
    query=f"""Question: {question}\n\nReference Answer:\n\n{reference_answer}\n\nAnswer to be evaluated:\n\n{candidate_answer}"""
    return query

def user_prompt(result1, result2, result3, chunks, candidate_answer,question):
    final_prompt="""##Inputs:"""
    accuracy_score=result1["score"]
    accuracy_diagnosis=result1["diagnosis"]
    accuracy_fix_instruction=result1["fix_instruction"]
    completeness_score=result2["score"]
    completeness_diagnosis=result2["diagnosis"]
    completeness_fix_instruction=result2["fix_instruction"]
    relevance_score=result3["score"]
    relevance_diagnosis=result3["diagnosis"]
    relevance_fix_instruction=result3["fix_instruction"]

    add_on=f"""RETRIEVED CHUNKS:
{chunks}

QUESTION:
{question}

CANDIDATE ANSWER:
{candidate_answer}

EVALUATION FEEDBACK:
Accuracy (score: {accuracy_score}/5) — {accuracy_diagnosis} FIX: {accuracy_fix_instruction}
Completeness (score: {completeness_score}/5) — {completeness_diagnosis} FIX: {completeness_fix_instruction}
Relevance (score: {relevance_score}/5) — {relevance_diagnosis} FIX: {relevance_fix_instruction}"""
    final_prompt+= "\n"
    final_prompt+=candidate_answer 
    final_prompt+=add_on
    return final_prompt


agent_acc=Agent(name="Accuracy evaluator", instructions=accuracy_instruction, model=llama_model, output_type=Scoring)
agent_com=Agent(name="compeletion evaluator", instructions=completeness_instruction, model=llama_model, output_type=Scoring)
agent_rel=Agent(name="relevance evaluator", instructions=relevance_instruction, model=llama_model, output_type=Scoring)
agent_rewriter=Agent(name="Answer rewriter", instructions=rewrite_instruction, model=llama_model)


async def running_para(query):
    results = await asyncio.gather(
    Runner.run(agent_acc, query),
    Runner.run(agent_com, query),
    Runner.run(agent_rel, query)
    )
    output=[json.loads(result.final_output.model_dump_json()) for result in results]  
    return output

def push(message):
    payload = {"user": pushover_user, "token": pushover_token, "message": message}
    requests.post(pushover_url, data=payload)


def select_the_best(memory):
    best_record = max(memory.history, key=lambda r: r.average_score)
    return best_record.model_dump_json()    


async def coach(question,reference_answer,iteration, memory, session):
    candidate_answer, chunks=answer_question(question)
    query=query_form(question, reference_answer, candidate_answer)
    results= await running_para(query)
    count=1
    print(any(result["score"] < 4.5 for result in results))
    average_score_weighted=(0.3*results[0]["score"]+0.5*results[1]["score"]+0.2*results[2]["score"])
    memory.add(
                iteration=0,
                average_score=average_score_weighted,
                current_answer=candidate_answer
            )
    while any(result["score"] < 4.5 for result in results) and count < iteration:
        average_score_weighted=(0.3*results[0]["score"]+0.5*results[1]["score"]+0.2*results[2]["score"])
        memory.add(
            iteration=count,
            average_score=average_score_weighted,
            current_answer=candidate_answer
        )
        prompt=user_prompt(results[0], results[1], results[2], chunks, candidate_answer, question)
        potential_answer=await Runner.run(agent_rewriter, prompt, session=session)
        count+=1
        candidate_answer=potential_answer.final_output
        query=query_form(question, reference_answer, candidate_answer)
        results=await running_para(query) 


async def improvement(test):
        session = SQLiteSession("12346")
        question = test.question
        reference_answer = test.reference_answer
        memory = Memory()
        await coach(
                question,
                reference_answer,
                iteration,
                memory,
                session,
                )
        record = select_the_best(memory)
        temp=json.loads(record)
        return temp["current_answer"]
        


