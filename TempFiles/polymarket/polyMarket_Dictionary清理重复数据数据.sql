/* 0) 可选：看下各表重复情况（执行完也能再跑对比） */
SELECT 'polyMarket_Dictionary' AS tbl, COUNT(*) AS total, COUNT(DISTINCT question) AS distinct_q
FROM polyMarket_Dictionary
UNION ALL
SELECT 'polyMarket_Dictionary_used' AS tbl, COUNT(*) AS total, COUNT(DISTINCT question) AS distinct_q
FROM polyMarket_Dictionary_used;


/* 1) 表内去重：polyMarket_Dictionary 只保留每个 question 的最小 rowid */
DELETE FROM polyMarket_Dictionary
WHERE question IS NOT NULL
  AND rowid NOT IN (
    SELECT MIN(rowid)
    FROM polyMarket_Dictionary
    WHERE question IS NOT NULL
    GROUP BY question
  );

/* 2) 表内去重：polyMarket_Dictionary_used 只保留每个 question 的最小 rowid */
DELETE FROM polyMarket_Dictionary_used
WHERE question IS NOT NULL
  AND rowid NOT IN (
    SELECT MIN(rowid)
    FROM polyMarket_Dictionary_used
    WHERE question IS NOT NULL
    GROUP BY question
  );

/* 3) 跨表去重：两表都存在同一 question 时，删掉 used 里的（保留 dictionary 里的） */
DELETE FROM polyMarket_Dictionary_used
WHERE question IS NOT NULL
  AND question IN (
    SELECT question
    FROM polyMarket_Dictionary
    WHERE question IS NOT NULL
  );

/* 4) 检查结果 */
SELECT 'polyMarket_Dictionary' AS tbl, COUNT(*) AS total, COUNT(DISTINCT question) AS distinct_q
FROM polyMarket_Dictionary
UNION ALL
SELECT 'polyMarket_Dictionary_used' AS tbl, COUNT(*) AS total, COUNT(DISTINCT question) AS distinct_q
FROM polyMarket_Dictionary_used;
