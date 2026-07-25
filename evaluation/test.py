from pydantic import BaseModel, Field
import json


class TestQuestion(BaseModel):
    question: str = Field(description="The question to ask the RAG system")
    keywords: list[str] = Field(description="Keywords that must appear in retrieved context")
    reference_answer: str = Field(description="The reference answer for this question")
    category: str = Field(description="Question category (e.g. preparedness_supply, family_plan)")


test_add=r"D:\disaster\Disaster-Management-RAG\evaluation\tests.jsonl"

def load_tests()-> list[TestQuestion]:
    tests=[]
    with open(test_add, "r", encoding="utf-8") as f:
        for line in f:
            data=json.loads(line.strip())
            tests.append(TestQuestion(**data))
    return tests         


