AUDIT (
  name assert_positive_revenue
);

SELECT *
FROM @this_model
WHERE revenue <= 0;
