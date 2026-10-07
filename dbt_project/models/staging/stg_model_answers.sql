select
    question_id,
    model,
    prompt_id,
    correct_letter,
    ai_answer,
    response_time,
    error
from {{ source('silver', 'model_answers') }}