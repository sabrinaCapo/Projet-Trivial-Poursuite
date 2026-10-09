-- Table de détail (une ligne par question) lue par le dashboard.
-- Les noms de colonnes sont ceux utilisés par app.py.
with int_data as (
    select * from {{ ref('int_llm_performance') }}
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
    is_correct as ai_correct,
    response_time_seconds as response_time,
    prompt_length_chars,
    is_hallucination,
    error_type,
    estimated_cpu_kwh
from int_data
