with joined as (
    select
        a.question_id,
        a.model,
        a.prompt_id,
        a.correct_letter,
        a.ai_answer,
        a.response_time,
        q.category,
        q.question_type,
        q.difficulty,
        -- lettre A-H en majuscule, seule ou suivie de . : ) (ex. "B", "B: Paris")
        nullif(
            regexp_extract(trim(a.ai_answer), '^\(?([A-H])\)?(?:[.:)]|$)', 1),
            ''
        ) as ai_letter
    from {{ ref('stg_model_answers') }} a
    join {{ ref('stg_questions') }} q using (question_id)
    where a.error is null
)

select
    *,
    ai_letter is not null as is_valid_format,
    coalesce(ai_letter = correct_letter, false) as ai_correct
from joined