(() => {
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
  const api = async (path) => {
    const response = await fetch(`/api${path}`, { credentials: 'same-origin' });
    if (!response.ok) throw new Error(`Le service local a répondu ${response.status}.`);
    return response.json();
  };
  const dateLabel = (run) => new Intl.DateTimeFormat('fr-CA', {
    dateStyle: 'medium', timeStyle: 'short'
  }).format(new Date(run.created_at));
  const jsonKey = (value) => JSON.stringify(value, (_key, item) => {
    if (!item || Array.isArray(item) || typeof item !== 'object') return item;
    return Object.fromEntries(Object.entries(item).sort(([left], [right]) => left.localeCompare(right)));
  });
  const normalized = (value) => String(value ?? '').normalize('NFKC').trim().toLocaleLowerCase('fr-CA');
  const sourceKey = (row) => [row.source, normalized(row.fichier), normalized(row.feuillet),
    normalized(row.type_element), normalized(row.element)].join('|');
  const labelArmature = (value) => {
    if (!Array.isArray(value) || !value.length) return 'Aucune armature lisible';
    return value.map((bar) => Object.entries(bar).filter(([, item]) => item !== null && item !== '')
      .map(([key, item]) => `${key}: ${item}`).join(' · ')).join(' / ');
  };
  const saveJson = (name, payload) => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url; link.download = name; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const compareExports = (older, newer, olderRun, newerRun) => {
    const grouped = new Map();
    const olderGrouped = new Map();
    for (const row of older) {
      const key = sourceKey(row);
      if (!olderGrouped.has(key)) olderGrouped.set(key, []);
      olderGrouped.get(key).push(row);
    }
    for (const row of newer) {
      const key = sourceKey(row);
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(row);
    }
    const claimed = new Set();
    const results = [];
    for (const before of older) {
      const possible = grouped.get(sourceKey(before)) || [];
      const nearby = possible.filter((after) => !claimed.has(after.id) &&
        Math.hypot(Number(before.x) - Number(after.x), Number(before.y) - Number(after.y)) <= 72);
      if (nearby.length !== 1) {
        results.push({ status: nearby.length ? 'ambiguous_candidate' : 'unpaired_review', before, after: null });
        continue;
      }
      const after = nearby[0];
      const reverse = (olderGrouped.get(sourceKey(after)) || []).filter((candidate) =>
        Math.hypot(Number(candidate.x) - Number(after.x), Number(candidate.y) - Number(after.y)) <= 72);
      if (reverse.length !== 1) {
        results.push({ status: 'ambiguous_candidate', before, after });
        continue;
      }
      claimed.add(after.id);
      results.push({ status: jsonKey(before.armature) === jsonKey(after.armature) ? 'same_candidate' : 'change_candidate', before, after });
    }
    for (const after of newer) if (!claimed.has(after.id)) results.push({ status: 'unpaired_review', before: null, after });
    return {
      schema_version: 1,
      scope: 'candidate revision comparison; no engineering decision',
      older_run: { id: olderRun.id, created_at: olderRun.created_at, source_sha256: olderRun.source_sha256 || null },
      newer_run: { id: newerRun.id, created_at: newerRun.created_at, source_sha256: newerRun.source_sha256 || null },
      counts: Object.fromEntries(['same_candidate', 'change_candidate', 'ambiguous_candidate', 'unpaired_review']
        .map((status) => [status, results.filter((row) => row.status === status).length])),
      limits: ['Correspondances candidates basées sur les métadonnées et une tolérance spatiale de 72 points.',
        'Les observations non appariées ne signifient pas manquant ou ajouté.',
        'Deux runs ne prouvent pas deux révisions PDF; vérifiez fichiers, empreintes et chaque valeur sur les sources.'],
      results: results.map((row) => ({
        status: row.status,
        before: row.before && { id: row.before.id, source: row.before.source, fichier: row.before.fichier,
          feuillet: row.before.feuillet, page: row.before.page, element: row.before.element,
          x: row.before.x, y: row.before.y, armature: row.before.armature },
        after: row.after && { id: row.after.id, source: row.after.source, fichier: row.after.fichier,
          feuillet: row.after.feuillet, page: row.after.page, element: row.after.element,
          x: row.after.x, y: row.after.y, armature: row.after.armature }
      }))
    };
  };

  window.renderQualityTools = async () => {
    document.body.dataset.view = 'quality';
    document.querySelectorAll('[data-nav]').forEach((link) => {
      const active = link.dataset.nav === 'quality';
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
    });
    document.querySelector('#crumb').innerHTML = '<span>Concorde</span> <span aria-hidden="true">/</span> <strong>Validation</strong>';
    document.title = 'Concorde · Validation';
    const view = document.querySelector('#view');
    view.innerHTML = `<div class="quality-page">
      <div class="eyebrow">CONCORDE / PREUVES ET BONUS</div>
      <header class="quality-heading"><div><h1>Comparer et vérifier</h1><p>Outils de revue locale pour les révisions, la confiance OCR et les sources PDF.</p></div><span class="quality-local"><i></i> Aucun envoi externe</span></header>
      <section class="quality-summary" aria-label="État de validation">
        <div><span class="quality-mark ready">●</span><strong>Couverture</strong><small>Les quatre projets terminés ont des exports contrôlés.</small></div>
        <div><span class="quality-mark review">◷</span><strong>Qualité métier</strong><small>Attend des références adjudiquées par un ingénieur.</small></div>
        <div><span class="quality-mark waiting">…</span><strong>Run actif</strong><small>Les outils de comparaison ne lancent pas d’OCR.</small></div>
      </section>
      <section class="card quality-card" aria-labelledby="revision-title">
        <div class="quality-card-head"><div><div class="eyebrow">BONUS · RÉVISIONS</div><h2 id="revision-title">Comparer deux analyses</h2><p>Compare les exports déjà terminés. Les changements sont des candidats à vérifier, jamais des verdicts.</p></div><span class="quality-number">01</span></div>
        <div class="quality-form-grid"><label class="field">Projet<select class="input" id="quality-project"><option value="">Chargement…</option></select></label><label class="field">Analyse précédente<select class="input" id="quality-older" disabled><option value="">Choisissez un projet</option></select></label><label class="field">Analyse récente<select class="input" id="quality-newer" disabled><option value="">Choisissez un projet</option></select></label></div>
        <div class="quality-actions"><button class="button primary" id="quality-compare" disabled>Comparer les exports</button><span class="small muted">Lecture locale de <code>informations.json</code>; aucune analyse n’est lancée.</span></div>
        <div id="quality-compare-state" class="quality-output" aria-live="polite"></div>
      </section>
      <section class="quality-grid">
        <article class="card quality-card"><div class="eyebrow">BONUS · PDF AVEC LIENS</div><h2>Annoter les sources</h2><p>Le script crée des copies annotées, ajoute des repères circulaires centrés sur X/Y et lie les pages correspondantes. Le cercle marque le centre exporté, pas le contour détecté de l’armature; les PDF originaux restent intacts.</p><ol><li>Téléchargez <code>informations.json</code> et <code>comparaisons.json</code> depuis Rapports.</li><li>Préparez un mapping local entre les noms PDF et leurs chemins sources.</li><li>Lancez <code>scripts/annotate_revision_pdf.py</code> avec un nouveau dossier de sortie sans anciens fichiers annotés.</li></ol><label class="field" for="quality-pdf-run">Analyse terminée<select class="input" id="quality-pdf-run"><option value="">Choisissez une analyse terminée</option></select></label><div class="quality-actions"><button class="button compact" id="quality-map" disabled>Préparer le mapping JSON</button><span class="small muted">Modèle sans chemin prérempli; associez les PDF sur votre poste.</span></div><details class="quality-details"><summary>Commande locale</summary><pre><code>python scripts/annotate_revision_pdf.py --informations informations.json --comparaisons comparaisons.json --source-map sources.json --output-dir annotations</code></pre></details><p class="notice-panel">Les couleurs signalent des propositions; elles ne certifient pas la structure.</p></article>
        <article class="card quality-card"><div class="eyebrow">BONUS · CONFIANCE</div><h2>Vérifier la calibration</h2><p>Le score OCR est brut. Il ne représente ni la probabilité que le texte soit exact, ni la conformité des armatures.</p><p>Une évaluation exige des labels d’ingénieur, une empreinte de run, un split indépendant par projet/document et une référence gelée.</p><details class="quality-details"><summary>Commande locale</summary><pre><code>python scripts/evaluate_confidence_calibration.py --reference reference.json --out calibration.json</code></pre><p>Le fichier de référence doit respecter le schéma documenté par le script. Aucun résultat ne devient une revendication de performance sans validation d’ingénieur.</p></details><p class="notice-panel warning">Aucune validation d’ingénieur n’a encore été faite. Le script garde cette limite dans son résultat.</p></article>
      </section>
      <section class="card quality-card quality-readiness"><div class="eyebrow">AVANT LA REMISE</div><h2>Vérifications encore nécessaires</h2><div class="quality-checks"><div><strong>Projet du jury</strong><span>Absent des fichiers locaux; la généralisation reste inconnue.</span></div><div><strong>Installation hors ligne</strong><span>Répéter sur le poste de remise avec les bibliothèques et poids préparés.</span></div><div><strong>Démonstration</strong><span>Répéter et chronométrer le parcours de dix minutes.</span></div><div><strong>Licence</strong><span>Confirmer que l’option PyMuPDF convient au mode de distribution.</span></div><div><strong>Confidentialité</strong><span>Confirmer le canal privé, ne pas exposer le serveur local et supprimer les données après l’événement.</span></div><div><strong>Labels d’ingénieur</strong><span>Faire adjudiquer les références, les vrais négatifs et les cas ambigus.</span></div></div></section>
    </div>`;
    const projectSelect = view.querySelector('#quality-project');
    const olderSelect = view.querySelector('#quality-older');
    const newerSelect = view.querySelector('#quality-newer');
    const pdfRunSelect = view.querySelector('#quality-pdf-run');
    const compareButton = view.querySelector('#quality-compare');
    const mappingButton = view.querySelector('#quality-map');
    const output = view.querySelector('#quality-compare-state');
    let overview;
    try {
      overview = await api('/overview');
      const done = (overview.jobs || []).filter((run) => run.status === 'completed');
      pdfRunSelect.innerHTML = '<option value="">Choisissez une analyse terminée</option>' + done.map((run) =>
        `<option value="${escapeHtml(run.id)}">${escapeHtml(run.project_name || run.project_id || 'Projet')} · ${escapeHtml(dateLabel(run))}</option>`).join('');
      pdfRunSelect.addEventListener('change', () => { mappingButton.disabled = !pdfRunSelect.value; });
      mappingButton.addEventListener('click', async () => {
        const run = done.find((item) => item.id === pdfRunSelect.value);
        if (!run) return;
        mappingButton.disabled = true; mappingButton.textContent = 'Préparation…';
        try {
          const response = await fetch(`/api/runs/${encodeURIComponent(run.id)}/download/informations.json`, { credentials: 'same-origin' });
          if (!response.ok) throw new Error('Export indisponible pour cette analyse terminée.');
          const information = await response.json();
          if (!Array.isArray(information)) throw new Error('Le format informations.json ne correspond pas au schéma attendu.');
          const filenames = [...new Set(information.map((row) => String(row.fichier || '').trim()).filter(Boolean))].sort();
          if (!filenames.length) throw new Error('Aucun nom de PDF source lisible dans cet export.');
          saveJson('sources-a-mapper.json', Object.fromEntries(filenames.map((name) => [name, 'CHEMIN_LOCAL_DU_PDF'])));
          output.innerHTML = `<p class="success-box" role="status">Modèle créé pour ${filenames.length} noms de PDF. Remplacez chaque valeur par le chemin local correspondant avant d’exécuter le script.</p>`;
        } catch (error) {
          output.innerHTML = `<div class="error-box" role="alert">${escapeHtml(error.message)}</div>`;
        } finally {
          mappingButton.disabled = !pdfRunSelect.value; mappingButton.textContent = 'Préparer le mapping JSON';
        }
      });
      const projects = overview.projects || [];
      projectSelect.innerHTML = '<option value="">Choisissez un projet</option>' + projects.map((project) =>
        `<option value="${escapeHtml(project.id)}">${escapeHtml(project.name)}</option>`).join('');
      projectSelect.addEventListener('change', () => {
        const runs = done.filter((run) => run.project_id === projectSelect.value)
          .sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
        const options = '<option value="">Choisissez une analyse terminée</option>' + runs.map((run) =>
          `<option value="${escapeHtml(run.id)}">${escapeHtml(dateLabel(run))} · ${escapeHtml(run.request?.profile || 'Analyse')}</option>`).join('');
        olderSelect.innerHTML = options; newerSelect.innerHTML = options;
        olderSelect.disabled = newerSelect.disabled = runs.length < 2;
        compareButton.disabled = runs.length < 2;
        output.innerHTML = runs.length < 2 ? '<p>Il faut deux analyses terminées du même projet.</p>' : '';
      });
      compareButton.addEventListener('click', async () => {
        if (!olderSelect.value || !newerSelect.value || olderSelect.value === newerSelect.value) {
          output.innerHTML = '<p class="error-box">Choisissez deux analyses différentes du même projet.</p>'; return;
        }
        const olderRun = done.find((run) => run.id === olderSelect.value);
        const newerRun = done.find((run) => run.id === newerSelect.value);
        if (!olderRun || !newerRun || olderRun.project_id !== newerRun.project_id) return;
        if (new Date(olderRun.created_at) >= new Date(newerRun.created_at)) {
          output.innerHTML = '<div class="error-box" role="alert">La version précédente doit être antérieure à la version récente.</div>'; return;
        }
        compareButton.disabled = true; compareButton.textContent = 'Comparaison locale…';
        output.innerHTML = '<p>Chargement des exports terminés. Aucun OCR n’est lancé.</p>';
        try {
          const [oldResponse, newResponse] = await Promise.all([
            fetch(`/api/runs/${encodeURIComponent(olderRun.id)}/download/informations.json`, { credentials: 'same-origin' }),
            fetch(`/api/runs/${encodeURIComponent(newerRun.id)}/download/informations.json`, { credentials: 'same-origin' })
          ]);
          if (!oldResponse.ok || !newResponse.ok) throw new Error('Un export n’est pas disponible. Sélectionnez deux runs terminés.');
          const [older, newer] = await Promise.all([oldResponse.json(), newResponse.json()]);
          if (!Array.isArray(older) || !Array.isArray(newer)) throw new Error('Le format informations.json ne correspond pas au schéma attendu.');
          const report = compareExports(older, newer, olderRun, newerRun);
          const priority = { change_candidate: 0, ambiguous_candidate: 1, unpaired_review: 2, same_candidate: 3 };
          report.results.sort((left, right) => priority[left.status] - priority[right.status]);
          const titles = { same_candidate: 'Même candidat · valeurs égales', change_candidate: 'Changement candidat · revue requise', ambiguous_candidate: 'Correspondance ambiguë', unpaired_review: 'À examiner · non apparié' };
          const total = report.results.length;
          let pageIndex = 0;
          let statusFilter = '';
          const pageSize = 120;
          const renderResults = () => {
            const filtered = report.results.filter((row) => !statusFilter || row.status === statusFilter);
            const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
            pageIndex = Math.min(pageIndex, pageCount - 1);
            const start = pageIndex * pageSize;
            const rows = filtered.slice(start, start + pageSize).map((row) => {
              const item = row.after || row.before;
              return `<tr><td>${escapeHtml(item?.feuillet || '—')}</td><td>${escapeHtml(item?.element || '—')}</td><td>${escapeHtml(titles[row.status])}</td><td>${escapeHtml(labelArmature(row.before?.armature))}</td><td>${escapeHtml(labelArmature(row.after?.armature))}</td></tr>`;
            }).join('');
            const first = filtered.length ? start + 1 : 0;
            const last = Math.min(start + pageSize, filtered.length);
            output.innerHTML = `<div class="quality-counts">${Object.entries(report.counts).map(([key, count]) => `<span><strong>${count}</strong> ${escapeHtml(titles[key])}</span>`).join('')}</div><p class="small muted">${escapeHtml(dateLabel(olderRun))} → ${escapeHtml(dateLabel(newerRun))}. ${total} lignes candidates.</p><div class="quality-results-tools"><label class="field">État<select class="input" id="quality-filter"><option value="">Tous les états</option>${Object.entries(titles).map(([key, title]) => `<option value="${key}">${escapeHtml(title)}</option>`).join('')}</select></label><span class="small muted">Lignes ${first}–${last} sur ${filtered.length}</span></div><div class="table-wrap quality-results"><table><thead><tr><th>Feuillet</th><th>Élément</th><th>État provisoire</th><th>Avant</th><th>Après</th></tr></thead><tbody>${rows || '<tr><td colspan="5">Aucune annotation dans ce groupe.</td></tr>'}</tbody></table></div><div class="quality-pagination"><button class="button compact ghost" id="quality-prev" ${pageIndex === 0 ? 'disabled' : ''}>Précédent</button><span class="small muted">Page ${pageIndex + 1} sur ${pageCount}</span><button class="button compact ghost" id="quality-next" ${pageIndex + 1 >= pageCount ? 'disabled' : ''}>Suivant</button><button class="button compact" id="quality-download">Télécharger le rapport JSON complet</button></div><ul class="small">${report.limits.map((limit) => `<li>${escapeHtml(limit)}</li>`).join('')}</ul>`;
            view.querySelector('#quality-filter').value = statusFilter;
            view.querySelector('#quality-filter').addEventListener('change', (event) => { statusFilter = event.currentTarget.value; pageIndex = 0; renderResults(); });
            view.querySelector('#quality-prev').addEventListener('click', () => { pageIndex -= 1; renderResults(); });
            view.querySelector('#quality-next').addEventListener('click', () => { pageIndex += 1; renderResults(); });
            view.querySelector('#quality-download').addEventListener('click', () => saveJson('comparaison-revisions-candidats.json', report));
          };
          renderResults();
        } catch (error) {
          output.innerHTML = `<div class="error-box" role="alert">${escapeHtml(error.message)}</div>`;
        } finally {
          compareButton.disabled = false; compareButton.textContent = 'Comparer les exports';
        }
      });
    } catch (error) {
      projectSelect.innerHTML = '<option value="">Projets indisponibles</option>';
      output.innerHTML = `<div class="error-box" role="alert">${escapeHtml(error.message)}</div>`;
    }
  };
})();
