-- Intermediate : indicateurs numériques prêts à être agrégés.
with staging as (
    select * from {{ ref('stg_questions_llm') }}
)

select
    category,
    type,
    difficulty,
    question,
    correct_answer,
    ai_model,
    ai_prompt_type,
    ai_answer,
    is_correct,
    case when is_correct then 1 else 0 end as is_correct_int,
    is_hallucination,
    case when is_hallucination then 1 else 0 end as is_hallucination_int,
    error_type,
    prompt_length_chars,
    estimated_cpu_kwh,
    response_time_seconds
from staging
