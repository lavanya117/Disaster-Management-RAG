from pydantic import BaseModel, Field
import math 
from .test import TestQuestion, load_tests
import sys
from implementation.answer import fetch_content, answer_question
from litellm import completion


MODEL='ollama/llama3.1:8b'

class  RetrievalEval(BaseModel):

    mrr: float = Field(description="Mean Reciprocal Rank - average across all keywords")
    ndcg: float = Field(description="Normalized Discounted Cumulative Gain (binary relevance)")
    keywords_found: int = Field(description="Number of keywords found in top-k results")
    total_keywords: int = Field(description="Total number of keywords to find")
    keyword_coverage: float = Field(description="Percentage of keywords found")






class AnswerEval(BaseModel):
    """LLM-as-a-judge evaluation of answer quality."""

    feedback: str = Field(
        description="Concise feedback on the answer quality, comparing it to the reference answer and evaluating based on the retrieved context"
    )
    accuracy: float = Field(
        description="How factually correct is the answer compared to the reference answer? 1 (wrong. any wrong answer must score 1) to 5 (ideal - perfectly accurate). An acceptable answer would score 3."
    )
    completeness: float = Field(
        description="How complete is the answer in addressing all aspects of the question? 1 (very poor - missing key information) to 5 (ideal - all the information from the reference answer is provided completely). Only answer 5 if ALL information from the reference answer is included."
    )
    relevance: float = Field(
        description="How relevant is the answer to the specific question asked? 1 (very poor - off-topic) to 5 (ideal - directly addresses question and gives no additional information). Only answer 5 if the answer is completely relevant to the question and gives no additional information."
    )






def calculate_mrr(keyword: str, retrived_doc: list) -> float:
    keyword_lower=keyword.lower()
    for rank, doc in enumerate(retrived_doc, start=1):
        if keyword_lower in doc.page_content.lower():
            return 1.0/rank
    return 0.0




def calculate_dcg(relevances: list[int], k: int ) -> float: #relevances is a list that consist of relevance scores for each doc in binary 
    dcg = 0.0
    for i in range(min(k, len(relevances))):
        dcg += relevances[i] / math.log2(i + 2)  # i+2 because rank starts at 1
    return dcg





def calculate_ndcg(keyword: str, retrived_docs: list, k: int =10) -> float:
    keyword_lower=keyword.lower()

    relevances=[1 if keyword_lower in doc.page_content.lower() else 0 for doc in retrived_docs]

    dcg=calculate_dcg(relevances, k)
    
    ideal_relevances=sorted(relevances, reverse=True)
    idcg=calculate_dcg(ideal_relevances, k)

    return dcg/idcg if idcg>0 else 0.0 




def evaluate_retrieval(test: TestQuestion, k: int = 10) -> RetrievalEval:
    
    retrieved_docs = fetch_content(test.question)

    # Calculate MRR 
    mrr_scores = [calculate_mrr(keyword, retrieved_docs) for keyword in test.keywords]
    avg_mrr = sum(mrr_scores) / len(mrr_scores) if mrr_scores else 0.0

    # Calculate nDCG (average across all keywords)
    ndcg_scores = [calculate_ndcg(keyword, retrieved_docs, k) for keyword in test.keywords]
    avg_ndcg = sum(ndcg_scores) / len(ndcg_scores) if ndcg_scores else 0.0

    # Calculate keyword coverage
    keywords_found = sum(1 for score in mrr_scores if score > 0)
    total_keywords = len(test.keywords)
    keyword_coverage = (keywords_found / total_keywords * 100) if total_keywords > 0 else 0.0

    return RetrievalEval(
        mrr=avg_mrr,
        ndcg=avg_ndcg,
        keywords_found=keywords_found,
        total_keywords=total_keywords,
        keyword_coverage=keyword_coverage,
    )




def evaluate_answer(test: TestQuestion) -> tuple[AnswerEval, str, list]:
    """
    Evaluate answer quality using LLM-as-a-judge (async).

    Args:
        test: TestQuestion object containing question and reference answer

    Returns:
        Tuple of (AnswerEval object, generated_answer string, retrieved_docs list)
    """

    generated_answer, retrieved_docs = answer_question(test.question)
    judge_messages = [
{
    "role": "system",
    "content": """
You are an impartial evaluator for a disaster preparedness question-answering system.

Your task is to compare a generated answer with a reference answer and assign scores based ONLY on factual content.

The reference answer is an example of a correct answer, not the only possible correct answer.

Important evaluation rules:

- Judge factual correctness, NOT writing style.
- Do NOT penalize:
  - different wording or paraphrasing
  - different sentence structure
  - different ordering of information
  - bullet points vs paragraphs
  - additional correct information not present in the reference
- Only reduce the accuracy score if the generated answer contains incorrect, misleading, unsupported, or contradictory facts.
- Only reduce the completeness score if important information from the reference answer is missing.
- Only reduce the relevance score if the generated answer fails to answer the user's question or contains substantial irrelevant content.

Scoring Guide

Accuracy (1-5)
5 = All factual information is correct.
4 = Mostly correct with only minor factual differences.
3 = Partially correct but contains some factual inaccuracies.
2 = Contains several factual errors.
1 = Clearly incorrect or directly contradicts the reference answer.

Completeness (1-5)
5 = Covers all important information from the reference answer.
4 = Covers most important information with minor omissions.
3 = Covers roughly half of the important information.
2 = Covers only a small portion of the important information.
1 = Covers little or none of the important information.

Relevance (1-5)
5 = Fully answers the question with no significant irrelevant content.
4 = Answers the question well with only minor unnecessary information.
3 = Partially answers the question.
2 = Mostly off-topic.
1 = Does not answer the question.

Return ONLY valid JSON in exactly this format:

{
  "feedback": "One or two concise sentences explaining the scores.",
  "accuracy": 1,
  "completeness": 1,
  "relevance": 1
}

Do not include markdown, explanations, code fences, or any additional text outside the JSON object.
"""
},
{
    "role": "user",
    "content": f"""
Question:
{test.question}

Generated Answer:
{generated_answer}

Reference Answer:
{test.reference_answer}

Evaluate the generated answer according to the scoring guide.

Remember:
- The reference answer is not the only correct answer.
- Judge factual correctness rather than wording.
- Do not penalize additional correct information.
- Return ONLY the JSON object.
"""
},
]

    # Call LLM judge with structured outputs 
    judge_response = completion(model=MODEL, messages=judge_messages, response_format=AnswerEval)

    answer_eval = AnswerEval.model_validate_json(judge_response.choices[0].message.content)

    return answer_eval, generated_answer, retrieved_docs




def evaluate_all_retrieval():

    tests = load_tests()
    total_tests = len(tests)
    for index, test in enumerate(tests):
        result = evaluate_retrieval(test)
        progress = (index + 1) / total_tests
        yield test, result, progress


def evaluate_all_answers():
    tests = load_tests()
    total_tests = len(tests)
    for index, test in enumerate(tests):
        result = evaluate_answer(test)[0]
        progress = (index + 1) / total_tests
        yield test, result, progress

def run_cli_evaluation(test_number: int):
    
    tests = load_tests("tests.jsonl")

    if test_number < 0 or test_number >= len(tests):
        print(f"Error: test_row_number must be between 0 and {len(tests) - 1}")
        sys.exit(1)

    test = tests[test_number]

    # test info
    print(f"\n{'=' * 80}")
    print(f"Test #{test_number}")
    print(f"{'=' * 80}")
    print(f"Question: {test.question}")
    print(f"Keywords: {test.keywords}")
    print(f"Category: {test.category}")
    print(f"Reference Answer: {test.reference_answer}")

    # Retrieval Evaluation
    print(f"\n{'=' * 80}")
    print("Retrieval Evaluation")
    print(f"{'=' * 80}")

    retrieval_result = evaluate_retrieval(test)

    print(f"MRR: {retrieval_result.mrr:.4f}")
    print(f"nDCG: {retrieval_result.ndcg:.4f}")
    print(f"Keywords Found: {retrieval_result.keywords_found}/{retrieval_result.total_keywords}")
    print(f"Keyword Coverage: {retrieval_result.keyword_coverage:.1f}%")

    # Answer Evaluation
    print(f"\n{'=' * 80}")
    print("Answer Evaluation")
    print(f"{'=' * 80}")

    answer_result, generated_answer, retrieved_docs = evaluate_answer(test)

    print(f"\nGenerated Answer:\n{generated_answer}")
    print(f"\nFeedback:\n{answer_result.feedback}")
    print("\nScores:")
    print(f"  Accuracy: {answer_result.accuracy:.2f}/5")
    print(f"  Completeness: {answer_result.completeness:.2f}/5")
    print(f"  Relevance: {answer_result.relevance:.2f}/5")
    print(f"\n{'=' * 80}\n")


def main():

    if len(sys.argv) != 2:
        print("Usage: uv run eval.py <test_row_number>")
        sys.exit(1)

    try:
        test_number = int(sys.argv[1])
    except ValueError:
        print("Error: test_row_number must be an integer")
        sys.exit(1)

    run_cli_evaluation(test_number)


if __name__ == "__main__":
    main()
