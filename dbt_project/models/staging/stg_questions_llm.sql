-- Staging : remise en forme de la silver (sans calcul métier).
-- - décode "&amp;" dans les catégories
-- - supprime les questions en double (garde la première par modèle, prompt et question)
with source as (
    select * from {{ source('silver_data', 'questions_llm') }}
)

select
    replace(category, '&amp;', '&') as category,
    type,
    difficulty,
    question,
    correct_answer,
    incorrect_answers,
    ai_model,
    ai_prompt_type,
    ai_answer,
    cast(ai_correct as boolean) as is_correct,
    cast(response_time as double) as response_time_seconds,
    prompt_length_chars,
    cast(is_hallucination as boolean) as is_hallucination,
    error_type,
    cast(estimated_cpu_kwh as double) as estimated_cpu_kwh
from source
qualify row_number() over (
    partition by ai_model, ai_prompt_type, question
    order by response_time
) = 1
