# Credibell
An AI-powered Loan Underwriting & Multi-Bank Eligibility Engine for Malaysian Consumers.

## Problem Statement
Applying for a loan can be complicated and frustration for a average joe. Customer would often need to rely on sales agents, bank agents or searching online on the loan application process, what documents that are needed, and what are the requirements for the loan approval. Even after submitting all the documents, the wait for the loan status often makes the applicants anxious, as they would need to plan for future arrangements, or if their loan application is rejected, they would need to quickly submit another application to another bank. Furthermore, any delays due to incomplete documents submitted or background of the applicants that may require further check may frustrate the applicant since the status is mostly undisclosed and requires further communications between the applicants and the banks, which is susceptible to miscommunication, or arguments happening. 

Existing digital application channels may simplify online submissions, but applicants can still struggle to understand their requirements and prepare complete applications before submitting them for review.

Credibell aims to address these challenges by providing an AI-powered, one-stop loan application assistant that automates document ingestion, extracts structured financial features, runs an explainable SHAP-backed credit risk model, and matches applicant profiles against real-time Malaysian bank lending criteria.

## Features:
1. Localized Document Ingestion
- Automated parsing and structured feature extraction from Malaysian financial documents:
  a. CCRIS & CTOS: Credit history, outstanding balances, DSR (Debt Service Ratio), and payment track record.
  b. EPF / KWSP & Payslips: Income verification, contribution consistency, and net monthly cash flow.

2. Hybrid Credit Scoring & Explainability Engine
- Deterministic Scoring: Quantitative ML scoring models that eliminate LLM math hallucinations.
- Explainable AI: Computes SHAP (SHapley Additive exPlanations) values for every decision, providing applicants and underwriters with exact feature attributions for approval or rejection.

3. RAG-Driven Multi-Bank Policy Matching
- Integrates RAG retrieval against structured bank policy rulebooks.
- Cross-references user financial profiles across local bank catalogs to suggest optimal loan products, tenures, and interest rates.
- Interactive "What-If" Loan Scenario Simulator

4. Production Engineering & Diagnostics
- Built-in diagnostic utilities for pipeline integrity, metric tracking, and comprehensive validation benchmarks.

## System Architecture

                                    +-----------------------+
                                    | Raw Document Uploads  |
                                    | (CCRIS, CTOS, EPF)    |
                                    +-----------+-----------+
                                                |
                                                v
                                    +-----------------------+
                                    | Document Parser       |
                                    | (documents.py)        |
                                    +-----------+-----------+
                                                |
                                                v
                                    +-----------------------+
                                    | Structured Feature    |
                                    | Extraction (schema.py)|
                                    +-----------+-----------+
                                                |
                    +---------------------------+---------------------------+
                    |                                                       |
                    v                                                       v
     +------------------------------+                       +------------------------------+
     |   Quantitative ML Engine     |                       |      RAG Retrieval Engine    |
     | (predictors.py / finance.py) |                       |   (retrieval.py / LLM)       |
     +--------------+---------------+                       +--------------+---------------+
                    |                                                       |
                    v                                                       v
     +------------------------------+                       +------------------------------+
     |  SHAP Explainability Engine  |                       |  Bank Policy Catalog Match   |
     |      (shap_engine.py)        |                       | (bank_catalog.json/policies) |
     +--------------+---------------+                       +--------------+---------------+
                    |                                                       |
                    +---------------------------+---------------------------+
                                                |
                                                v
                                    +-----------------------+
                                    | Comprehensive Credit  |
                                    | & Eligibility Report  |
                                    +-----------------------+

## Tech Stack
- Frontend: Streamlit
- Backend: Python FastAPI

## Prerequisite
- Python 3.10 or higher
- Virtual environment tool (env)

## How to Run
- A start.cmd has been implemented for fast and easier execution.

## Team Members (LunchBuddies)
1. Lucius Long Kai Xuan
2. Tey Kaize
3. Darren Yap Zhen Jie
4. Shamin Hossain






