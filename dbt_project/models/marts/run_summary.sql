select
    model,
    prompt_id,
    count(distinct question_id) as nb_questions,
    count(*) as nb_calls,
    count(*) filter (where error is not null) as nb_errors,
    (select count(*) from {{ ref('stg_questions') }}) as total_questions
from {{ ref('stg_model_answers') }}
group by model, prompt_id