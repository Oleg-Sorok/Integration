#!/usr/bin/env bash
# Black-box acceptance test. Usage: bash scripts/check.sh   (stack must be running)
O=${ORDERS_URL:-http://localhost:8000}
ok(){ echo "  OK  - $1"; }; bad(){ echo "  FAIL- $1"; FAILED=1; }
code(){ curl -s -o /dev/null -w '%{http_code}' "$@"; }
BODY='{"client_name":"Alice Brown","gr_liv_area":2000,"total_bsmt_sf":1200,"garage_area":550,"year_built":2000,"overall_qual":8,"ms_zoning":"RL"}'
J='Content-Type: application/json'

echo "== 1. health"; [ "$(code $O/health)" = 200 ] && ok orders || bad orders

echo "== 2. create order (forecast UP)"
R=$(curl -s -X POST $O/orders -H "$J" -d "$BODY"); echo "$R"
ID=$(echo "$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
P1=$(echo "$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["predicted_price"])')
[ "$P1" != None ] && ok "price=$P1" || bad "price is null although forecast is up"

echo "== 3. PATCH client_name only -> price unchanged"
P2=$(curl -s -X PATCH $O/orders/$ID -H "$J" -d '{"client_name":"Alice Cooper"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["predicted_price"])')
[ "$P1" = "$P2" ] && ok "unchanged" || bad "price changed: $P2"

echo "== 4. PATCH overall_qual 8->4 -> price must be recalculated"
P3=$(curl -s -X PATCH $O/orders/$ID -H "$J" -d '{"overall_qual":4,"gr_liv_area":1200}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["predicted_price"])')
[ "$P3" != "$P1" ] && [ "$P3" != None ] && ok "new price=$P3" || bad "price not recalculated ($P3)"

echo "== 5. validation"
[ "$(code -X PATCH $O/orders/$ID -H "$J" -d '{"overall_qual":99}')" = 422 ] && ok "422 on bad value" || bad "no 422"
[ "$(code -X PATCH $O/orders/$ID -H "$J" -d '{"gr_liv_area":null}')" = 422 ] && ok "422 on null" || bad "no 422 on null"
[ "$(code -X PATCH $O/orders/999999 -H "$J" -d '{"overall_qual":5}')" = 404 ] && ok "404" || bad "no 404"

echo "== 6. FORECAST DOWN (graceful degradation)"
docker compose stop forecast-api >/dev/null 2>&1
R=$(curl -s -X POST $O/orders -H "$J" -d "$BODY"); echo "$R"
echo "$R" | grep -q '"predicted_price":null' && ok "order created with predicted_price=null" || bad "order not created"
ID2=$(echo "$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
R=$(curl -s -X PATCH $O/orders/$ID2 -H "$J" -d '{"overall_qual":5}')
echo "$R" | grep -q '"predicted_price":null' && ok "PATCH works, price=null" || bad "PATCH failed: $R"

echo "== 7. orders-api survives restart with forecast DOWN"
docker compose restart orders-api >/dev/null 2>&1; sleep 4
[ "$(code $O/health)" = 200 ] && ok "orders-api up without forecast" || bad "orders-api did not start"

echo "== 8. forecast back -> PATCH recomputes price"
docker compose start forecast-api >/dev/null 2>&1; sleep 8
P4=$(curl -s -X PATCH $O/orders/$ID2 -H "$J" -d '{"overall_qual":6}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["predicted_price"])')
[ "$P4" != None ] && ok "price restored=$P4" || bad "still null"

curl -s -X DELETE $O/orders/$ID -o /dev/null; curl -s -X DELETE $O/orders/$ID2 -o /dev/null
[ -z "$FAILED" ] && echo "ALL CHECKS PASSED" || { echo "SOME CHECKS FAILED"; exit 1; }
