with per_question as (
    select
        model,
        question_id,
        bool_or(ai_correct) filter (where prompt_id = 'p1_english')  as en_ok,
        bool_or(ai_correct) filter (where prompt_id = 'p2_français') as fr_ok
    from {{ ref('int_answers_scored') }}
    group by model, question_id
)

select
    model,
    count(*) as nb_questions,
    round(100.0 * avg((en_ok = fr_ok)::int), 2) as same_result_pct,
    round(100.0 * avg((en_ok and fr_ok)::int), 2) as both_correct_pct,
    round(100.0 * avg((not en_ok and not fr_ok)::int), 2) as both_wrong_pct,
    round(100.0 * avg((en_ok and not fr_ok)::int), 2) as only_en_correct_pct,
    round(100.0 * avg((not en_ok and fr_ok)::int), 2) as only_fr_correct_pct
from per_question
where en_ok is not null and fr_ok is not null
group by model