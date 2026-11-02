-- PS-QUOTE-RULES dev examples. Read-only. Crew: run on the dev copy, mask names before posting.
-- 1. Who can approve today (role names only, rule Q1).
select r.name as role_name, count(distinct ur.user_id) as users
from user_permissions p
join user_role_permissions rp on rp.permission_id = p.id
join user_roles r on r.id = rp.role_id
left join user_role_assignments ur on ur.role_id = r.id
where p.slug = 'projects.quotations.approve'
group by r.name order by r.name;

-- 2. The project ladder: does final_negotiation exist, and its sort_order vs the others (rule 7b).
select key, label, sort_order, is_terminal, is_active
from statuses where entity_type = 'project' and scope_id is null order by sort_order;

-- 3. Documents whose current lines carry off-series and/or below-floor lines (rules 1, 6).
select d.document_no, st.key as project_stage, pr.is_critical,
       sum(case when l.is_non_standard then 1 else 0 end) as off_series_lines,
       sum(case when l.is_below_floor then 1 else 0 end) as below_floor_lines,
       a.key as approval_key
from projects.quotation_documents d
join projects.projects pr on pr.id = d.project_id
left join statuses st on st.id = pr.status_id
left join statuses a on a.id = d.approval_status_id
join projects.quotations q on q.document_id = d.id
join projects.quotation_versions v on v.quotation_id = q.id
  and v.version_no = (select max(v2.version_no) from projects.quotation_versions v2
                      where v2.quotation_id = q.id)
join projects.quotation_lines l on l.version_id = v.id
group by d.document_no, st.key, pr.is_critical, a.key
having sum(case when l.is_non_standard or l.is_below_floor then 1 else 0 end) > 0
order by d.document_no desc limit 10;
