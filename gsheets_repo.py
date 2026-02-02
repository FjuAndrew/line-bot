    def summary_by_category(
        self,
        group_id: str,
        start_iso: str,
        end_iso: str,
        category: str | None = None,
    ) -> dict:
        """
        回傳：
          - total_amount
          - total_count
          - by_category: {category: {"amount": x, "count": y}}
        若 category 有給，則只統計該類別（by_category 仍會回傳單一類別）
        """
        rows = self.ws_records.get_all_records()
        total_amount = 0
        total_count = 0
        by_cat: dict[str, dict] = {}

        for r in rows:
            if str(r.get("group_id", "")) != group_id:
                continue

            ts = str(r.get("ts", ""))
            if not (start_iso <= ts < end_iso):
                continue

            cat = str(r.get("category", "") or "未分類")
            if category and cat != category:
                continue

            amt = int(r.get("amount", 0) or 0)

            total_amount += amt
            total_count += 1

            if cat not in by_cat:
                by_cat[cat] = {"amount": 0, "count": 0}
            by_cat[cat]["amount"] += amt
            by_cat[cat]["count"] += 1

        # 依金額排序（回傳前端再排也可）
        by_cat = dict(sorted(by_cat.items(), key=lambda kv: kv[1]["amount"], reverse=True))

        return {
            "total_amount": total_amount,
            "total_count": total_count,
            "by_category": by_cat,
        }
