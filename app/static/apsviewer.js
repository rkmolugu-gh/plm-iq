(function () {
    'use strict';

    let viewer = null;
    let currentUrn = null;

    const statusEl = document.getElementById('viewer-status');
    const selectEl = document.getElementById('model-select');
    const loadBtn = document.getElementById('load-model');
    const translateBtn = document.getElementById('translate-model');

    function setStatus(message, kind) {
        statusEl.textContent = message;
        statusEl.className = 'alert ' + (kind || 'alert-info') + (message ? ' d-block' : ' d-none');
    }

    function clearStatus() {
        setStatus('', 'alert-info');
    }

    function showError(message) {
        setStatus(message, 'alert-danger');
        console.error(message);
    }

    function getAccessToken(callback) {
        fetch('/apsviewer/api/token')
            .then(function (resp) { return resp.json(); })
            .then(function (token) {
                callback(token.access_token, token.expires_in);
            })
            .catch(function (err) {
                console.error(err);
                if (window.Autodesk && window.Autodesk.Viewing) {
                    // Surface the error in the viewer overlay if available.
                }
            });
    }

    async function listModels() {
        const resp = await fetch('/apsviewer/api/models');
        if (!resp.ok) {
            throw new Error(await resp.text());
        }
        const data = await resp.json();
        selectEl.innerHTML = '<option value="">— Select a model —</option>';
        const models = data.models || [];
        models.forEach(function (m) {
            const opt = document.createElement('option');
            opt.value = m.filename;
            opt.textContent = m.filename;
            selectEl.appendChild(opt);
        });
        loadBtn.disabled = translateBtn.disabled = models.length === 0;
    }

    function initViewer() {
        return new Promise(function (resolve, reject) {
            if (viewer) { resolve(viewer); return; }
            Autodesk.Viewing.Initializer({ env: 'AutodeskProduction', getAccessToken }, function () {
                viewer = new Autodesk.Viewing.GuiViewer3D(document.getElementById('viewer'), { extensions: ['Autodesk.DocumentBrowser'] });
                viewer.start();
                viewer.setTheme('light-theme');
                resolve(viewer);
            });
        });
    }

    async function translateSelected() {
        const filename = selectEl.value;
        if (!filename) { return; }
        translateBtn.disabled = true;
        setStatus('Sending ' + filename + ' to APS for translation…', 'alert-info');
        try {
            const resp = await fetch('/apsviewer/api/models/' + encodeURIComponent(filename) + '/translate', { method: 'POST' });
            const data = await resp.json();
            if (!resp.ok) {
                throw new Error(data.error || ('HTTP ' + resp.status));
            }
            setStatus('Translation job accepted for ' + filename + '. Polling status…', 'alert-info');
            await pollStatus(filename);
        } catch (err) {
            showError('Translation failed: ' + err.message);
        } finally {
            clearStatus();
            translateBtn.disabled = false;
            loadBtn.disabled = selectEl.value === '';
        }
    }

    async function pollStatus(filename) {
        const url = '/apsviewer/api/models/' + encodeURIComponent(filename) + '/status';
        for (let i = 0; i < 60; i++) {
            const resp = await fetch(url);
            const data = await resp.json();
            if (!resp.ok) {
                throw new Error(data.error || ('HTTP ' + resp.status));
            }
            const status = data.status;
            if (status === 'success') {
                currentUrn = data.urn;
                setStatus('Translation complete. Click Load to view.', 'alert-success');
                return;
            }
            if (status === 'failed') {
                const detail = (data.messages || []).map(function (m) { return JSON.stringify(m); }).join(', ');
                throw new Error('Translation failed: ' + detail);
            }
            setStatus('Translating ' + filename + ' (' + (data.progress || '…') + ')' +
                (status === 'n/a' ? ' — not started yet.' : '…'), 'alert-info');
            await new Promise(function (r) { setTimeout(r, 5000); });
        }
        throw new Error('Timed out waiting for translation.');
    }

    async function loadSelected() {
        const filename = selectEl.value;
        if (!filename) { return; }
        // Reuse the current urn if already translated; otherwise look it up.
        if (!currentUrn) {
            const resp = await fetch('/apsviewer/api/models/' + encodeURIComponent(filename) + '/status');
            const data = await resp.json();
            if (data.urn) { currentUrn = data.urn; }
        }
        if (!currentUrn) {
            showError('This model has no translation yet. Click Translate first.');
            return;
        }
        await initViewer();
        setStatus('Loading ' + filename + '…', 'alert-info');
        Autodesk.Viewing.Document.load('urn:' + currentUrn, function (doc) {
            viewer.loadDocumentNode(doc, doc.getRoot().getDefaultGeometry());
            clearStatus();
        }, function (errCode, errMsg) {
            showError('Could not load model: ' + errMsg);
        });
    }

    selectEl.onchange = function () {
        loadBtn.disabled = translateBtn.disabled = selectEl.value === '';
    };
    loadBtn.onclick = loadSelected;
    translateBtn.onclick = translateSelected;

    listModels().catch(function (err) {
        showError('Could not list models: ' + err.message);
    });
})();
