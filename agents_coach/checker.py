import sys
from pathlib import Path

project_root = Path.cwd().parent
sys.path.insert(0, str(project_root))

from implementation.answer import answer_question
from agents import Agent, Runner, SQLiteSession, OpenAIChatCompletionsModel, set_tracing_disabled, RunConfig, ModelSettings
from openai import AsyncOpenAI
import json
from pydantic import BaseModel, Field
import asyncio
from tqdm import tqdm
import os
import requests
import asyncio
import uuid
from .prompts import accuracy_instruction, completeness_instruction, rewrite_instruction, relevance_instruction, accuracy_instruction_user, completeness_instruction_user, relevance_instruction_user


pushover_user = os.getenv("PUSHOVER_USER")
pushover_token = os.getenv("PUSHOVER_TOKEN")
pushover_url = "https://api.pushover.net/1/messages.json"
model="llama3.1:8b"
model_eval="gemma3:4b"
iteration=3
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
gemma_model=OpenAIChatCompletionsModel(model=model_eval, openai_client=ollama_client)
model_settings=ModelSettings(
    temperature=0.0,
    max_tokens=512,)

def query_form(question,reference_answer,candidate_answer,chunks):
    if reference_answer:
        query=f"""Question: {question}\n\nReference Answer:\n\n{reference_answer}\n\nAnswer to be evaluated:\n\n{candidate_answer}"""
    else:
        query=f"""USER QUESTION:\n\n{question}\n\nRETRIEVED CONTEXT\n\n{chunks}\n\nGENERATED ANSWER:\n\n{candidate_answer}"""    
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

def agent_creation(for_evals):
    if for_evals:
        agent_acc=Agent(name="Accuracy evaluator", instructions=accuracy_instruction, model=gemma_model, output_type=Scoring)
        agent_com=Agent(name="compeletion evaluator", instructions=completeness_instruction, model=gemma_model, output_type=Scoring)
        agent_rel=Agent(name="relevance evaluator", instructions=relevance_instruction, model=gemma_model, output_type=Scoring)
    else:
        agent_acc=Agent(name="Accuracy evaluator", instructions=accuracy_instruction_user, model=gemma_model, output_type=Scoring)
        agent_com=Agent(name="compeletion evaluator", instructions=completeness_instruction_user, model=gemma_model, output_type=Scoring)
        agent_rel=Agent(name="relevance evaluator", instructions=relevance_instruction_user, model=gemma_model, output_type=Scoring)
    return agent_acc, agent_com, agent_rel



agent_rewriter=Agent(name="Answer rewriter", instructions=rewrite_instruction, model=llama_model) 



async def running_para(query, agent_acc, agent_com, agent_rel):
    results = await asyncio.gather(
    Runner.run(agent_acc, query, run_config=RunConfig(model_settings)),
    Runner.run(agent_com, query, run_config=RunConfig(model_settings)),
    Runner.run(agent_rel, query, run_config=RunConfig(model_settings))
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
    query=query_form(question, reference_answer, candidate_answer,None)
    for_evals=True
    agent_acc, agent_com, agent_rel = agent_creation(for_evals)
    results= await running_para(query, agent_acc, agent_com, agent_rel)
    count=1
    average_score_weighted=(0.3*results[0]["score"]+0.5*results[1]["score"]+0.2*results[2]["score"])
    previous_score=average_score_weighted
    memory.add(
                iteration=0,
                average_score=average_score_weighted,
                current_answer=candidate_answer
            )
    while any(result["score"] < 4.5 for result in results) and count < iteration:
        prompt=user_prompt(results[0], results[1], results[2], chunks, candidate_answer, question)
        potential_answer=await Runner.run(agent_rewriter, prompt, session=session, run_config=RunConfig(model_settings))
        count+=1
        candidate_answer=potential_answer.final_output
        query=query_form(question, reference_answer, candidate_answer, None)
        results=await running_para(query, agent_acc, agent_com, agent_rel)
        average_score_weighted=(0.3*results[0]["score"]+0.5*results[1]["score"]+0.2*results[2]["score"])
        if previous_score>=average_score_weighted:
            break
        previous_score=average_score_weighted
        memory.add(
                iteration=count,
                average_score=average_score_weighted,
                current_answer=candidate_answer
                )
                 


async def coach_user(question,iteration, memory, session, history): #for the gradio app
    candidate_answer, chunks=answer_question(question, history)
    query=query_form(question, None, candidate_answer, chunks)
    for_evals=False
    agent_acc, agent_com, agent_rel = agent_creation(for_evals)
    results= await running_para(query, agent_acc, agent_com, agent_rel)
    count=1
    average_score_weighted=(0.3*results[0]["score"]+0.5*results[1]["score"]+0.2*results[2]["score"])
    previous_score=average_score_weighted
    memory.add(
                iteration=0,
                average_score=average_score_weighted,
                current_answer=candidate_answer
            )
    while any(result["score"] < 4 for result in results) and count < iteration:
        prompt=user_prompt(results[0], results[1], results[2], chunks, candidate_answer, question)
        potential_answer=await Runner.run(agent_rewriter, prompt, session=session, run_config=RunConfig(model_settings=ModelSettings(max_tokens=2048, temperature=0.0)))
        count+=1
        candidate_answer=potential_answer.final_output
        query=query_form(question, None, candidate_answer, chunks)
        results=await running_para(query, agent_acc, agent_com, agent_rel) 
        average_score_weighted=(0.3*results[0]["score"]+0.5*results[1]["score"]+0.2*results[2]["score"])
        if previous_score>=average_score_weighted:
            break
        previous_score=average_score_weighted
        memory.add(
                    iteration=count,
                    average_score=average_score_weighted,
                    current_answer=candidate_answer
                )

async def improvement(test):
        session = SQLiteSession(str(uuid.uuid4()))
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
        

async def evaluate_rag(question, history): 
    session=SQLiteSession(str(uuid.uuid4()))
    memory = Memory()
    await coach_user(
                question,
                iteration,
                memory,
                session,
                history
                )
    record = select_the_best(memory)
    temp=json.loads(record)
    full_answer= temp["current_answer"]
    if full_answer:
        push("It is Done!")
    chunk_size=12
    for i in range(0, len(full_answer), chunk_size):
        yield full_answer[i:i + chunk_size]
        await asyncio.sleep(0.02)
