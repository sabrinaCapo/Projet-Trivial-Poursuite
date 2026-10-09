-- Question métier : quand le modèle se trompe, choisit-il une mauvaise option plausible
-- ou invente-t-il une réponse hors des options (hallucination) ?
with int_data as (
    select * from {{ ref('int_llm_performance') }}
)

select
    ai_model,
    error_type,
    count(*) as total_questions,
    round(count(*) * 100.0 / sum(count(*)) over (partition by ai_model), 2) as share_pct
from int_data
group by 1, 2
