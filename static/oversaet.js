/* Customs Analytics — Oversæt: upload én angivelse, se den i begge formater.
   Renderer felt-par fra /api/oversaet og kobler dem med tovejs-highlight. */

(function () {
    "use strict";

    var esc = function (s) {
        return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
        });
    };

    var FIELD_INDEX = {};   // uid -> feltdata (til panelet)
    var pinned = null;

    function fieldRow(f, side, uid) {
        var meta = side === "sad" ? f.sad : f.dms;
        var no = side === "sad" ? (meta.box || "—") : meta.de;
        var value = f.value == null ? "— (ikke i kilden)" : f.value;
        var missing = f.value == null ? " missing" : "";
        return (
            '<div class="ovs-field" data-uid="' + uid + '" tabindex="0">' +
            '<span class="no">' + esc(no) + "</span>" +
            '<span class="vl' + missing + '">' + esc(value) + "</span>" +
            '<span class="lb">' + esc(meta.label) + "</span>" +
            "</div>"
        );
    }

    function docHtml(data, side) {
        var html = '<div class="ovs-doc-body">';
        html += '<div class="ovs-sec">Hoveddel</div>';
        data.header_fields.forEach(function (f) {
            var uid = "h:" + f.key;
            FIELD_INDEX[uid] = f;
            html += fieldRow(f, side, uid);
        });
        data.item_sections.forEach(function (sec, i) {
            html += '<div class="ovs-sec">Varepost ' + esc(sec.item_number || i + 1) + "</div>";
            sec.fields.forEach(function (f) {
                var uid = "i" + i + ":" + f.key;
                FIELD_INDEX[uid] = f;
                html += fieldRow(f, side, uid);
            });
        });
        return html + "</div>";
    }

    var wrap = document.getElementById("ovs-panelwrap");
    var panel = document.getElementById("ovs-panel");

    function showPanel(f) {
        panel.innerHTML =
            '<span class="st st-' + esc(f.status) + '">' + esc(f.status_label) + "</span>" +
            '<span class="pair">' + esc((f.sad.box || "Ingen rubrik") + " " + f.sad.label) +
            " ⇄ " + esc(f.dms.de + " " + f.dms.label) + "</span>" +
            '<span class="note">' + esc(f.note || "") + "</span>";
        wrap.classList.add("show");
    }

    function hidePanel() { wrap.classList.remove("show"); }

    function setHl(uid, cls, on) {
        document.querySelectorAll('.ovs-field[data-uid="' + uid + '"]').forEach(function (el) {
            el.classList.toggle(cls, on);
        });
    }

    function bindInteractions() {
        document.querySelectorAll(".ovs-field").forEach(function (el) {
            var uid = el.getAttribute("data-uid");
            el.addEventListener("mouseenter", function () { setHl(uid, "hl", true); showPanel(FIELD_INDEX[uid]); });
            el.addEventListener("mouseleave", function () {
                setHl(uid, "hl", false);
                if (pinned) showPanel(FIELD_INDEX[pinned]); else hidePanel();
            });
            el.addEventListener("focus", function () { setHl(uid, "hl", true); showPanel(FIELD_INDEX[uid]); });
            el.addEventListener("blur", function () { setHl(uid, "hl", false); if (!pinned) hidePanel(); });
            el.addEventListener("click", function (ev) {
                ev.stopPropagation();
                if (pinned === uid) { setHl(uid, "pin", false); pinned = null; hidePanel(); return; }
                if (pinned) setHl(pinned, "pin", false);
                pinned = uid; setHl(uid, "pin", true); showPanel(FIELD_INDEX[uid]);
            });
            el.addEventListener("keydown", function (ev) {
                if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); el.click(); }
            });
        });
        document.addEventListener("click", function () { if (pinned) { setHl(pinned, "pin", false); pinned = null; } hidePanel(); });
        document.addEventListener("keydown", function (ev) {
            if (ev.key === "Escape") { if (pinned) { setHl(pinned, "pin", false); pinned = null; } hidePanel(); }
        });
    }

    var FORMAT_LABELS = {
        wco_xml: "DMS-XML (nyt format)",
        dms_pdf: "DMS-print (PDF, nyt format)",
        legacy_sad: "Gammelt toldsystem (PDF)",
        tabular: "Struktureret udtræk (CSV/XLSX)",
    };

    function render(data) {
        FIELD_INDEX = {}; pinned = null; hidePanel();
        document.getElementById("empty-state").hidden = true;
        document.getElementById("result").hidden = false;

        document.getElementById("ovs-format").textContent = "Genkendt: " + (FORMAT_LABELS[data.source_format] || data.source_format);
        document.getElementById("ovs-direction").textContent =
            data.direction === "ny_til_gammel"
                ? "Ny angivelse oversat til den gamle rubrikstruktur — og vist i begge formater."
                : "Gammel angivelse oversat til DMS-dataelementer — og vist i begge formater.";

        var cov = data.coverage;
        document.getElementById("ovs-coverage-fill").style.width = Math.round((cov.filled / cov.total) * 100) + "%";
        document.getElementById("ovs-coverage-text").textContent =
            cov.filled + " af " + cov.total + " felter udlæst af kilden" +
            (cov.missing_keys.length ? " · " + cov.missing_keys.length + " felttyper mangler" : "");
        document.getElementById("ovs-lossy").hidden = !data.lossy_source;

        document.getElementById("sad-body").innerHTML = docHtml(data, "sad");
        document.getElementById("dms-body").innerHTML = docHtml(data, "dms");
        bindInteractions();
    }

    async function uploadFile(file) {
        var err = document.getElementById("upload-error");
        err.hidden = true;
        try {
            var fd = new FormData();
            fd.append("file", file);
            var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
            var res = await fetch("/api/oversaet", { method: "POST", body: fd, headers: { "X-CSRF-Token": csrf } });
            var data = await res.json();
            if (!res.ok) { err.textContent = data.error || "Kunne ikke læse filen."; err.hidden = false; return; }
            render(data);
        } catch (e) {
            err.textContent = "Netværksfejl — prøv igen."; err.hidden = false;
        }
    }

    var fileInput = document.getElementById("file-input");
    fileInput.addEventListener("change", function (e) { if (e.target.files[0]) uploadFile(e.target.files[0]); });
    document.getElementById("empty-upload-btn").addEventListener("click", function () { fileInput.click(); });
})();
