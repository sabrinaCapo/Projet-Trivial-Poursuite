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
        q.correct_answer,
        a.prompt_id = 'p3_libre' as is_free
    from {{ ref('stg_model_answers') }} a
    join {{ ref('stg_questions') }} q using (question_id)
    where a.error is null
),

cleaned as (
    select
        *,
        -- prompts à choix : lettre A-H en majuscule (ex. "B", "B: Paris")
        case when not is_free then
            nullif(regexp_extract(trim(ai_answer), '^\(?([A-H])\)?(?:[.:)]|$)', 1), '')
        end as ai_letter,
        -- prompt libre : textes normalisés (minuscules, sans accents ni ponctuation)
        trim(regexp_replace(regexp_replace(
            lower(strip_accents(coalesce(ai_answer, ''))),
            '[^\p{L}\p{N}\s]', ' ', 'g'), '\s+', ' ', 'g')) as ai_clean,
        trim(regexp_replace(regexp_replace(
            lower(strip_accents(correct_answer)),
            '[^\p{L}\p{N}\s]', ' ', 'g'), '\s+', ' ', 'g')) as ref_clean
    from joined
)

select
    *,
    case when is_free then ai_clean <> '' else ai_letter is not null end as is_valid_format,
    case
        when is_free and question_type = 'boolean' then ai_clean = ref_clean
        when is_free then ref_clean <> ''
            and contains(' ' || ai_clean || ' ', ' ' || ref_clean || ' ')
        else coalesce(ai_letter = correct_letter, false)
    end as ai_correct
from cleaned