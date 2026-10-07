select
    model,
    prompt_id,
    difficulty,
    ai_correct,
    count(*) as nb_answers,
    round(avg(response_time), 3) as avg_response_time,
    round(median(response_time), 3) as median_response_time
from {{ ref('int_answers_scored') }}
group by model, prompt_id, difficulty, ai_correct