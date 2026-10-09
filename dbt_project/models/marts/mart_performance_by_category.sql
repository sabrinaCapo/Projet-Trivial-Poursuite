with int_data as (
    select * from {{ ref('int_llm_performance') }}
)

select
    ai_model,
    category,
    count(*) as total_questions,
    sum(is_correct_int) as total_correct,
    round((sum(is_correct_int) * 100.0 / count(*)), 2) as accuracy_pct,
    round(avg(response_time_seconds), 3) as avg_response_time_sec
from int_data
group by 1, 2