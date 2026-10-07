select
    model,
    prompt_id,
    category,
    count(*) as nb_answers,
    round(100.0 * avg(ai_correct::int), 2) as accuracy_pct
from {{ ref('int_answers_scored') }}
group by model, prompt_id, category