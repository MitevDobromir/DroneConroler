#!/bin/bash
# vendor_fuel_models.sh
# ---------------------------------------------------------------------------
# Vendors the Gazebo Fuel models the worlds actually use, so the sim runs fully
# offline afterwards.
#
#   * NO DRIFT: the models to vendor are derived by parsing Worlds/*.sdf for
#     model://<name> (XML-parsed, so comments/prose are ignored). Add a Fuel
#     <include> to any world and it is picked up automatically.
#   * VENDOR-AS-REFERENCED-NAME: each model is vendored into Models/<name>
#     using the EXACT model:// string from the world, so resolution can't break
#     on capitalization/spacing differences with the Fuel name.
#   * REAL LICENSES: license + author come from Fuel's REST API and the model's
#     model.config — never guessed.
#   * ANIMAL SLOT: a referenced name listed in ANIMAL_SLOTS (default "Animal")
#     is satisfied by searching Fuel for any animal (cow/sheep/goat/...) and
#     vendoring the first that downloads — handy when you just want "an animal".
#
# Run on the VM (needs internet once):  cd ~/ROS2_Tools/Scripts && ./vendor_fuel_models.sh
# ---------------------------------------------------------------------------
set -uo pipefail

ROOT="${ROOT:-$HOME/ROS2_Tools}"
WORLDS_DIR="${WORLDS_DIR:-$ROOT/Worlds}"
VENDOR_DIR="${VENDOR_DIR:-$ROOT/Models}"
ACK_FILE="${ACK_FILE:-$ROOT/ACKNOWLEDGEMENTS.md}"
FUEL_CACHE="$HOME/.gz/fuel/fuel.gazebosim.org"
FUEL_API="https://fuel.gazebosim.org/1.0"

# model:// name  ->  full Fuel URL (supplies the owner for that name)
declare -A FUEL_MODELS=(
  ["Ambulance"]="$FUEL_API/OpenRobotics/models/Ambulance"
  ["Oak tree"]="$FUEL_API/OpenRobotics/models/Oak tree"
  ["Pine Tree"]="$FUEL_API/OpenRobotics/models/Pine Tree"
)
# Referenced names to satisfy with "any animal" found on Fuel.
ANIMAL_SLOTS=("Animal")
ANIMAL_TERMS=(cow sheep goat horse deer pig donkey llama dog cat chicken duck goose bull)
# ---------------------------------------------------------------------------

c_ok="\033[0;32m"; c_warn="\033[0;33m"; c_err="\033[0;31m"; c_inf="\033[0;36m"; c_off="\033[0m"
ok(){ echo -e "${c_ok}[OK]${c_off} $*"; }; warn(){ echo -e "${c_warn}[WARN]${c_off} $*"; }
err(){ echo -e "${c_err}[ERR]${c_off} $*"; }; inf(){ echo -e "${c_inf}[INFO]${c_off} $*"; }

for dep in gz curl python3; do command -v "$dep" >/dev/null 2>&1 || { err "'$dep' not in PATH. Source your Gazebo/ROS env."; exit 1; }; done
[ -d "$WORLDS_DIR" ] || { err "Worlds dir not found: $WORLDS_DIR"; exit 1; }
mkdir -p "$VENDOR_DIR"

urlencode(){ python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$1"; }

# Query Fuel search API for a term; print "owner/Name" lines (robust to shape).
fuel_search(){
  local enc; enc="$(urlencode "$1")"
  curl -fsSL "$FUEL_API/models?q=$enc&per_page=20" 2>/dev/null | python3 - "$1" <<'PY'
import sys, json
q=sys.argv[1].lower()
try: data=json.load(sys.stdin)
except Exception: data=[]
items = data if isinstance(data,list) else (data.get("models",[]) if isinstance(data,dict) else [])
items.sort(key=lambda m: m.get("name","").lower()!=q)
for m in items[:20]:
    o=m.get("owner") or m.get("Owner") or ""; n=m.get("name") or m.get("Name") or ""
    if o and n: print(f"{o}/{n}")
PY
}

# license<TAB>license_url<TAB>author  (API + model.config author)
fetch_meta(){
  local owner="$1" name="$2" cfg="$3" enc json
  enc="$(urlencode "$name")"; json="$(curl -fsSL "$FUEL_API/$owner/models/$enc" 2>/dev/null || true)"
  CFG="$cfg" python3 - "$json" <<'PY'
import os,sys,json,xml.etree.ElementTree as ET
lic=licurl=auth=""
try:
    d=json.loads(sys.argv[1]); lic=(d.get("license_name") or "").strip(); licurl=(d.get("license_url") or "").strip()
except Exception: pass
try:
    a=ET.parse(os.environ.get("CFG","")).getroot().find(".//author/name")
    if a is not None and a.text: auth=a.text.strip()
except Exception: pass
print("\t".join([lic or "UNKNOWN - verify on Fuel page", licurl or "-", auth or "UNKNOWN"]))
PY
}

# Download a Fuel URL and vendor it into Models/<asname>. Echoes the version dir on success.
vendor_as(){
  local url="$1" asname="$2" fuel_name cached vdir dest
  gz fuel download -v 1 -u "$url" >/dev/null 2>&1 || return 1
  fuel_name="$(basename "$url")"
  cached="$(find "$FUEL_CACHE" -type d -ipath "*/models/$fuel_name" 2>/dev/null | head -n1)"
  [ -z "$cached" ] && return 1
  vdir="$(find "$cached" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -n1)"
  [ -z "$vdir" ] || [ ! -f "$vdir/model.config" ] && return 1
  dest="$VENDOR_DIR/$asname"; rm -rf "$dest"; cp -r "$vdir" "$dest"; touch "$dest/.vendored_from_fuel"
  echo "$dest"
}

is_animal_slot(){ local n; for n in "${ANIMAL_SLOTS[@]}"; do [ "$n" = "$1" ] && return 0; done; return 1; }

# ---- 1. Scan worlds (XML-parsed; comments ignored) ------------------------
inf "Scanning $WORLDS_DIR for model:// references ..."
mapfile -t REQUIRED < <(python3 - "$WORLDS_DIR"/*.sdf <<'PY'
import sys, xml.etree.ElementTree as ET
names=set()
for p in sys.argv[1:]:
    try: root=ET.parse(p).getroot()
    except Exception as e: sys.stderr.write(f"[scan] skip {p}: {e}\n"); continue
    for u in root.iter('uri'):
        t=(u.text or '').strip()
        if t.startswith('model://'): names.add(t[len('model://'):].strip())
for n in sorted(names): print(n)
PY
)
[ ${#REQUIRED[@]} -eq 0 ] && { warn "No model:// references found. Nothing to vendor."; exit 0; }
inf "Worlds reference ${#REQUIRED[@]} model(s): ${REQUIRED[*]}"

# ---- 2. Acknowledgements header -------------------------------------------
{ echo "# Third-Party Asset Acknowledgements"; echo
  echo "_Generated by Scripts/vendor_fuel_models.sh on $(date -u '+%Y-%m-%d %H:%M UTC')._"; echo
  echo "Models sourced from [Gazebo Fuel](https://app.gazebosim.org/fuel), vendored locally."
  echo "License + author read from Fuel metadata and model.config at vendor time."; echo
} > "$ACK_FILE"

VENDORED=(); FAILED=(); UNRESOLVED=(); LOCAL=()

write_ack(){ # url owner asname dest
  local url="$1" owner="$2" asname="$3" dest="$4" LIC LICURL AUTH
  IFS=$'\t' read -r LIC LICURL AUTH < <(fetch_meta "$owner" "$(basename "$url")" "$dest/model.config")
  echo "  License: $LIC"; echo "  Author:  $AUTH"
  { echo "## $asname"; echo "- Source: <$url>"; echo "- Author: $AUTH"; echo "- License: $LIC"
    [ "$LICURL" != "-" ] && echo "- License URL: <$LICURL>"
    echo "- Vendored to: \`${dest#$ROOT/}\`"; echo; } >> "$ACK_FILE"
}
owner_of(){ echo "$1" | sed -E 's#.*/1\.0/([^/]+)/models/.*#\1#'; }

# ---- 3. Resolve + vendor each referenced model ----------------------------
for name in "${REQUIRED[@]}"; do
  echo; echo "=============================================================="; echo "Model: $name"
  url="${FUEL_MODELS[$name]+${FUEL_MODELS[$name]}}"

  # (a) registered URL
  if [ -n "${url:-}" ]; then
    echo "  URL: $url"
    dest="$(vendor_as "$url" "$name")" && { ok "Vendored -> $dest"; VENDORED+=("$name"); write_ack "$url" "$(owner_of "$url")" "$name" "$dest"; } \
      || { err "Download failed for '$name'."; FAILED+=("$name"); }
    continue
  fi

  # (b) already a local (non-Fuel) model
  if [ -d "$VENDOR_DIR/$name" ] && [ -f "$VENDOR_DIR/$name/model.sdf" ] && [ ! -f "$VENDOR_DIR/$name/.vendored_from_fuel" ]; then
    inf "Local (non-Fuel) model present; leaving as-is."; LOCAL+=("$name"); continue
  fi

  # (c) animal slot: find any animal on Fuel
  if is_animal_slot "$name"; then
    inf "Animal slot '$name' — searching Fuel for an animal ..."
    picked=""
    for term in "${ANIMAL_TERMS[@]}"; do
      mapfile -t cands < <(fuel_search "$term")
      for c in "${cands[@]}"; do
        o="${c%%/*}"; n="${c#*/}"; curl_url="$FUEL_API/$o/models/$n"
        dest="$(vendor_as "$curl_url" "$name")" || continue
        ok "Found animal: $c  ->  vendored as model://$name"
        VENDORED+=("$name"); write_ack "$curl_url" "$o" "$name" "$dest"; picked="$c"; break 2
      done
    done
    [ -z "$picked" ] && { err "No downloadable animal found on Fuel."; UNRESOLVED+=("$name"); }
    continue
  fi

  # (d) generic: try to resolve an unregistered name by exact search
  inf "No URL registered for '$name' — searching Fuel ..."
  mapfile -t cands < <(fuel_search "$name")
  if [ ${#cands[@]} -gt 0 ]; then
    first="${cands[0]}"; o="${first%%/*}"; n="${first#*/}"; curl_url="$FUEL_API/$o/models/$n"
    dest="$(vendor_as "$curl_url" "$name")" \
      && { ok "Resolved '$name' -> $first; vendored as model://$name"; VENDORED+=("$name"); write_ack "$curl_url" "$o" "$name" "$dest"; } \
      || { err "Found $first but download failed."; FAILED+=("$name"); }
  else
    err "Could not resolve '$name' on Fuel, not local."; UNRESOLVED+=("$name")
  fi
done

# ---- 4. Summary + drift report --------------------------------------------
echo; echo "=============================================================="
[ ${#VENDORED[@]} -gt 0 ] && { ok "Vendored ${#VENDORED[@]} model(s):"; for n in "${VENDORED[@]}"; do echo "    model://$n"; done; }
[ ${#LOCAL[@]}   -gt 0 ] && inf "Local (non-Fuel), left as-is: ${LOCAL[*]}"
[ ${#FAILED[@]}  -gt 0 ] && warn "Download failed: ${FAILED[*]}"
if [ ${#UNRESOLVED[@]} -gt 0 ]; then
  err "UNRESOLVED: ${UNRESOLVED[*]}"
  err "Discover manually on the VM:  gz fuel list -t model -r 2>/dev/null | grep -iE 'cow|sheep|goat|animal'"
fi
for key in "${!FUEL_MODELS[@]}"; do u=0; for r in "${REQUIRED[@]}"; do [ "$r" = "$key" ] && u=1; done; [ $u -eq 0 ] && inf "Registry entry '$key' unused by any world."; done
echo; ok "Acknowledgements -> $ACK_FILE"
{ [ ${#FAILED[@]} -gt 0 ] || [ ${#UNRESOLVED[@]} -gt 0 ]; } && exit 1 || exit 0