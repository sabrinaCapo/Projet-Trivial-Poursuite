select
    model,
    prompt_id,
    count(*) as nb_answers,
    round(100.0 * avg(ai_correct::int), 2) as accuracy_pct,
    round(100.0 * avg(is_valid_format::int), 2) as valid_format_pct,
    round(avg(response_time), 3) as avg_response_time
from {{ ref('int_answers_scored') }}
group by model, prompt_id