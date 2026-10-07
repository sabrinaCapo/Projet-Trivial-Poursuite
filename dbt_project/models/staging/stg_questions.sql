select
    question_id,
    category,
    type as question_type,
    difficulty,
    question,
    correct_answer,
    incorrect_answers,
    scraped_at
from {{ source('silver', 'questions_clean') }}