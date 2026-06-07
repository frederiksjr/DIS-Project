const form = document.getElementById('recommend-form');
const loadingId = document.getElementById('loading');
const errorMsg = document.getElementById('error-msg');
const resultsArea = document.getElementById('results-area');
const inputs = document.querySelectorAll('.chips button[data-val]');

inputs.forEach(btn => { btn.addEventListener('click', (e) => { 
    form.querySelector('#query').value = e.target.dataset.val; 
    generateMovies(e.target.value);
}); });

function toggleState(state) {
    if(state === 'loading') { loadingId.classList.remove('hidden'); resultsArea.classList.add('hidden'); errorMsg.classList.add('hidden'); }
    else if (state === 'error') { errorMsg.classList.remove('hidden'); loadingId.classList.add('hidden'); resultsArea.classList.add('hidden'); }
    else { loadingId.classList.add('hidden'); errorMsg.classList.add('hidden'); resultsArea.classList.remove('hidden'); }
}

async function generateMovies(prompt) {
    toggleState('loading');
    document.getElementById('generate-btn').disabled = true;
    
    try {
        // Update this URL if your endpoint is different (e.g., /api/recommend)
        const res = await fetch('/ui/api/recommend', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, 
            body: JSON.stringify({ query: prompt })
        });
        !res.ok ? throw new Error('API Error') : false; 
        const data = await res.json();
        
        resultsArea.innerHTML = '';
        if(!data.movies.length) resultsArea.innerHTML = '<div style="text-align:center;color:var(--muted);padding:1rem">No matches found.</div>';

        data.movies.forEach(m => {
            const card = document.createElement('div'); 
            card.className = 'movie-card';
            card.innerHTML = `
                <div class="poster-placeholder"></div>
                <div class="card-info">
                    <h3 class="movie-title">${m.title}</h3>
                    <div class="movie-meta"><span>${m.year || 'N/A'}</span> • <span>${(m.genres||[])[0] || 'Unknown'}</span></div>
                    <p style="font-size:0.9rem;line-height:1.5;color:#ccc;margin-bottom:0.6rem">${m.overview || 'No synopsis available.'}</p>
                    ${m.match_reason ? `<span class="match-reason">🎯 Reason: ${m.match_reason}</span>` : ''}
                </div>`;
            resultsArea.appendChild(card);
        });
        toggleState('success');
    } catch (err) {
        console.error(err);
        toggleState('error');
    } finally { document.getElementById('generate-btn').disabled = false; }
}
