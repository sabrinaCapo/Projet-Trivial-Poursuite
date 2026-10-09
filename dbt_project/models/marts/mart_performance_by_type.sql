-- Question métier : le type de question (QCM ou vrai/faux) change-t-il le score ?
-- Hasard : 25 % en QCM (4 choix), 50 % en vrai/faux.
with int_data as (
    select * from {{ ref('int_llm_performance') }}
)

select
    ai_model,
    type,
    count(*) as total_questions,
    sum(is_correct_int) as total_correct,
    round((sum(is_correct_int) * 100.0 / count(*)), 2) as accuracy_pct,
    case type when 'multiple' then 25.0 when 'boolean' then 50.0 end as chance_level_pct,
    round(avg(response_time_seconds), 3) as avg_response_time_sec
from int_data
group by 1, 2
