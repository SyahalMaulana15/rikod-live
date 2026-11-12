// Rikod Live - Frontend Application Logic

let activeTab = 'live';
let liveStreams = [];
let allRecordings = [];
let allMembers = [];
let appStatus = {};
let hlsInstance = null;

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    loadAppStatus();
    loadLiveStreams();
    loadMembers();
    loadSettings();
    loadRecordings();

    // Periodic pollers
    setInterval(loadAppStatus, 3000);
    setInterval(loadLiveStreams, 15000);
    setInterval(() => {
        if (activeTab === 'recordings') loadRecordings();
    }, 3000);
});

// Toast notification helper
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast pointer-events-auto flex items-center space-x-2 px-4 py-2.5 rounded-xl text-xs font-medium shadow-xl border ${
        type === 'success' ? 'bg-emerald-950 border-emerald-800 text-emerald-200' :
        type === 'error' ? 'bg-rose-950 border-rose-800 text-rose-200' :
        'bg-slate-900 border-slate-700 text-slate-200'
    }`;
    
    const icon = type === 'success' ? 'fa-circle-check text-emerald-400' :
                 type === 'error' ? 'fa-circle-exclamation text-rose-400' :
                 'fa-circle-info text-sky-400';

    toast.innerHTML = `<i class="fa-solid ${icon}"></i><span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Tab navigation
function switchTab(tabId) {
    activeTab = tabId;
    document.querySelectorAll('.tab-pane').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.nav-tab').forEach(el => {
        el.classList.remove('text-rose-400', 'bg-rose-500/10', 'border', 'border-rose-500/20');
        el.classList.add('text-slate-400');
    });

    const targetContent = document.getElementById(`tab-content-${tabId}`);
    const targetBtn = document.getElementById(`tab-btn-${tabId}`);

    if (targetContent) targetContent.classList.remove('hidden');
    if (targetBtn) {
        targetBtn.classList.remove('text-slate-400');
        targetBtn.classList.add('text-rose-400', 'bg-rose-500/10', 'border', 'border-rose-500/20');
    }

    if (tabId === 'recordings') loadRecordings();
    if (tabId === 'members') loadMembers();
}

// Format bytes
function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i];
}

// Format duration
function formatDuration(seconds) {
    if (!seconds) return '00:00';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) {
        return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

// --- STATUS & STATS ---
async function loadAppStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        appStatus = data;

        // Update Header stats
        const activeCount = (data.active_recordings || []).length;
        document.getElementById('stat-recording-count').textContent = activeCount;
        
        const badge = document.getElementById('tab-recording-badge');
        if (activeCount > 0) {
            badge.textContent = activeCount;
            badge.classList.remove('hidden');
        } else {
            badge.classList.add('hidden');
        }

        const freeGb = (data.storage.free_bytes / (1024 ** 3)).toFixed(1);
        document.getElementById('stat-free-disk').textContent = `${freeGb} GB Bebas`;

        // Render Active Recordings
        renderActiveRecordings(data.active_recordings || []);

        // Master auto record toggle state
        const masterToggle = document.getElementById('master-auto-record');
        if (masterToggle) {
            masterToggle.checked = data.settings.auto_record_all_jkt48;
        }
    } catch (e) {
        console.warn('Failed to load status:', e);
    }
}

// --- LIVE STREAMS ---
async function loadLiveStreams() {
    try {
        const res = await fetch('/api/live');
        const data = await res.json();
        liveStreams = data.streams || [];
        
        document.getElementById('tab-live-count').textContent = liveStreams.length;
        renderLiveStreams();
    } catch (e) {
        console.warn('Failed to load live streams:', e);
    }
}

async function forceRefreshLive() {
    const icon = document.getElementById('refresh-icon');
    icon.classList.add('fa-spin');
    try {
        const res = await fetch('/api/live/check', { method: 'POST' });
        const data = await res.json();
        liveStreams = data.streams || [];
        document.getElementById('tab-live-count').textContent = liveStreams.length;
        renderLiveStreams();
        showToast('Pengecekan siaran IDN Live selesai.', 'success');
    } catch (e) {
        showToast('Gagal memeriksa live stream.', 'error');
    } finally {
        setTimeout(() => icon.classList.remove('fa-spin'), 600);
    }
}

function renderLiveStreams() {
    const container = document.getElementById('live-streams-container');
    const jktOnly = document.getElementById('filter-jkt48-only').checked;

    let filtered = liveStreams;
    const jktCount = liveStreams.filter(s => s.is_jkt48).length;

    if (jktOnly) {
        filtered = liveStreams.filter(s => s.is_jkt48);
    }

    if (filtered.length === 0) {
        if (liveStreams.length > 0 && jktOnly) {
            container.innerHTML = `
                <div class="col-span-full py-12 text-center text-slate-400 bg-slate-900/40 rounded-2xl border border-slate-800">
                    <div class="w-12 h-12 mx-auto rounded-full bg-slate-800 flex items-center justify-center text-rose-500 mb-3">
                        <i class="fa-solid fa-users text-xl"></i>
                    </div>
                    <p class="text-sm font-semibold text-white">Ditemukan ${liveStreams.length} siaran aktif di IDN App, namun belum terdeteksi tag JKT48.</p>
                    <p class="text-xs text-slate-400 mt-1">Anda dapat melihat semua siaran untuk memilih live member secara manual.</p>
                    <button onclick="document.getElementById('filter-jkt48-only').checked=false; renderLiveStreams();" class="mt-4 px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-lg shadow-lg shadow-rose-900/30 transition">
                        <i class="fa-solid fa-eye mr-1.5"></i> Tampilkan Semua ${liveStreams.length} Siaran
                    </button>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="col-span-full py-16 text-center text-slate-500 bg-slate-900/40 rounded-2xl border border-slate-800/80">
                <div class="w-12 h-12 mx-auto rounded-full bg-slate-800 flex items-center justify-center text-slate-600 mb-3">
                    <i class="fa-solid fa-tower-broadcast text-xl"></i>
                </div>
                <p class="text-sm font-semibold text-slate-300">Tidak ada siaran live yang terdeteksi saat ini.</p>
                <p class="text-xs text-slate-500 mt-1">Aplikasi memantau otomatis via API IDN & JKT48 Tracker.</p>
                <div class="flex items-center justify-center space-x-3 mt-4">
                    <button onclick="forceRefreshLive()" class="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-lg border border-slate-700 transition">
                        <i class="fa-solid fa-arrows-rotate mr-1.5"></i> Periksa Ulang Sekarang
                    </button>
                    <button onclick="openManualRecordModal()" class="px-3.5 py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-medium rounded-lg shadow-md shadow-rose-900/30 transition">
                        <i class="fa-solid fa-link mr-1.5"></i> Masukkan Link Live Manual
                    </button>
                </div>
            </div>
        `;
        return;
    }

    container.innerHTML = filtered.map(s => {
        const isRecording = s.is_recording;
        const creator = s.creator || {};
        const avatar = creator.avatar || 'https://via.placeholder.com/80/1e293b/ffffff?text=JKT48';
        const cover = s.image_url || 'https://via.placeholder.com/400x225/0f172a/ffffff?text=IDN+Live';

        return `
            <div class="bg-slate-900 rounded-2xl border ${s.is_jkt48 ? 'border-rose-900/50 hover:border-rose-600/80' : 'border-slate-800 hover:border-slate-700'} overflow-hidden transition-all duration-300 shadow-lg flex flex-col justify-between group">
                <div>
                    <!-- Stream Cover & Badges -->
                    <div class="relative aspect-video bg-black overflow-hidden">
                        <img src="${cover}" alt="${s.title}" class="w-full h-full object-cover group-hover:scale-105 transition duration-500">
                        <div class="absolute inset-0 bg-gradient-to-t from-slate-950 via-transparent to-black/60"></div>
                        
                        <!-- Live Indicator -->
                        <div class="absolute top-2.5 left-2.5 flex items-center space-x-1.5 bg-rose-600 text-white text-[10px] font-bold px-2 py-0.5 rounded-md shadow-md uppercase tracking-wider">
                            <span class="w-1.5 h-1.5 rounded-full bg-white animate-pulse"></span>
                            <span>LIVE</span>
                        </div>

                        <!-- Viewer Count -->
                        <div class="absolute top-2.5 right-2.5 bg-black/60 backdrop-blur text-white text-[10px] font-medium px-2 py-0.5 rounded-md flex items-center space-x-1">
                            <i class="fa-solid fa-eye text-rose-400 text-[9px]"></i>
                            <span>${(s.view_count || 0).toLocaleString()}</span>
                        </div>

                        <!-- Preview Button Overlay -->
                        <button onclick="previewStream('${s.playback_url}', '${encodeURIComponent(s.title)}', '${encodeURIComponent(creator.name)}')" class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 bg-black/40 backdrop-blur-xs transition duration-200 text-white">
                            <div class="w-10 h-10 rounded-full bg-rose-600/90 flex items-center justify-center shadow-lg transform group-hover:scale-110 transition">
                                <i class="fa-solid fa-play text-sm ml-0.5"></i>
                            </div>
                        </button>
                    </div>

                    <!-- Stream Details -->
                    <div class="p-4">
                        <div class="flex items-start space-x-3">
                            <img src="${avatar}" alt="${creator.name}" class="w-10 h-10 rounded-full object-cover border-2 border-rose-500/40 flex-shrink-0">
                            <div class="min-w-0 flex-1">
                                <div class="flex items-center space-x-1.5">
                                    <h4 class="text-xs font-bold text-white truncate hover:text-rose-400 transition cursor-pointer" onclick="window.open('https://www.idn.app/@${creator.username}', '_blank')">
                                        ${creator.name}
                                    </h4>
                                    ${creator.is_verified ? '<i class="fa-solid fa-circle-check text-sky-400 text-[10px]"></i>' : ''}
                                </div>
                                <p class="text-[11px] text-slate-400 truncate">@${creator.username}</p>
                                <p class="text-xs text-slate-200 font-medium mt-1.5 line-clamp-2 leading-relaxed" title="${s.title}">
                                    ${s.title}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Footer Action Buttons -->
                <div class="p-4 pt-0">
                    <div class="border-t border-slate-800/80 pt-3 flex items-center space-x-2">
                        <button onclick="previewStream('${s.playback_url}', '${encodeURIComponent(s.title)}', '${encodeURIComponent(creator.name)}')" class="flex-1 py-1.5 px-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg text-center transition">
                            <i class="fa-solid fa-play mr-1 text-[10px]"></i> Tonton
                        </button>

                        ${isRecording ? `
                            <button onclick="stopRecordingBySlug('${s.slug}')" class="flex-1 py-1.5 px-2 bg-rose-600/20 border border-rose-500/40 text-rose-300 hover:bg-rose-600 hover:text-white text-xs font-semibold rounded-lg text-center transition flex items-center justify-center space-x-1">
                                <span class="w-2 h-2 rounded-full bg-rose-500 animate-ping"></span>
                                <span>Stop Rekam</span>
                            </button>
                        ` : `
                            <button onclick="startManualRecordBySlug('${s.slug}')" class="flex-1 py-1.5 px-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-lg text-center shadow-md shadow-rose-900/30 transition">
                                <i class="fa-solid fa-circle-dot mr-1 text-[10px]"></i> Rekam
                            </button>
                        `}
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// --- ACTIVE RECORDINGS ---
function renderActiveRecordings(sessions) {
    const container = document.getElementById('active-recordings-container');
    if (!sessions || sessions.length === 0) {
        container.innerHTML = `
            <div class="py-16 text-center text-slate-500 bg-slate-900/50 rounded-2xl border border-slate-800/80">
                <i class="fa-solid fa-record-vinyl text-4xl mb-3 text-slate-600"></i>
                <p class="text-sm font-medium">Tidak ada proses perekaman yang sedang berjalan.</p>
                <p class="text-xs text-slate-500 mt-1">Sesi akan otomatis muncul jika ada member live yang masuk ke watchlist auto-record.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = sessions.map(s => {
        const durationStr = formatDuration(s.elapsed_seconds);
        const sizeStr = formatBytes(s.file_size);

        return `
            <div class="p-4 rounded-xl bg-slate-900 border border-rose-900/40 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div class="flex items-center space-x-4">
                    <div class="w-12 h-12 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-500 text-xl flex-shrink-0 animate-pulse">
                        <i class="fa-solid fa-record-vinyl"></i>
                    </div>
                    <div>
                        <div class="flex items-center space-x-2">
                            <span class="text-xs font-bold text-white">${s.member_name}</span>
                            <span class="text-[10px] bg-rose-500/20 text-rose-400 font-semibold px-2 py-0.5 rounded-full border border-rose-500/30 uppercase">RECORDING</span>
                            <span class="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded uppercase">${s.engine}</span>
                        </div>
                        <p class="text-xs text-slate-300 font-medium mt-0.5 truncate max-w-md">${s.title}</p>
                        <p class="text-[11px] text-slate-500 mt-0.5 font-mono">${s.file_name}</p>
                    </div>
                </div>

                <div class="flex items-center space-x-6 w-full sm:w-auto justify-between sm:justify-end border-t sm:border-0 border-slate-800 pt-3 sm:pt-0">
                    <div class="text-right">
                        <p class="text-xs text-slate-400">Durasi: <strong class="text-white font-mono">${durationStr}</strong></p>
                        <p class="text-xs text-slate-400">Ukuran: <strong class="text-white font-mono">${sizeStr}</strong> (${s.speed_kbps} KB/s)</p>
                    </div>

                    <button onclick="stopRecordingTask('${s.task_id}')" class="px-4 py-2 bg-rose-600/20 hover:bg-rose-600 text-rose-300 hover:text-white border border-rose-500/40 rounded-lg text-xs font-semibold transition flex items-center space-x-1.5">
                        <i class="fa-solid fa-stop"></i>
                        <span>Stop Rekam</span>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

// --- RECORDINGS GALLERY ---
async function loadRecordings() {
    try {
        const res = await fetch('/api/recordings');
        const data = await res.json();
        allRecordings = data.recordings || [];
        renderRecordingsTable(allRecordings);
    } catch (e) {
        console.warn('Failed to load recordings:', e);
    }
}

function filterRecordings() {
    const query = document.getElementById('recordings-search').value.toLowerCase();
    const filtered = allRecordings.filter(r => 
        (r.member_name || '').toLowerCase().includes(query) ||
        (r.title || '').toLowerCase().includes(query) ||
        (r.file_name || '').toLowerCase().includes(query)
    );
    renderRecordingsTable(filtered);
}

function renderRecordingsTable(records) {
    const tbody = document.getElementById('recordings-table-body');
    if (!records || records.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="px-4 py-12 text-center text-slate-500">
                    Belum ada rekaman yang tersimpan.
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = records.map(r => {
        const durStr = formatDuration(r.duration);
        const sizeStr = formatBytes(r.file_size);
        const dateStr = r.created_at ? new Date(r.created_at).toLocaleString('id-ID', { dateStyle: 'short', timeStyle: 'short' }) : '--';

        let cloudBadge = '<span class="text-slate-500">Belum di-upload</span>';
        if (r.cloud_status === 'uploaded') {
            cloudBadge = r.cloud_url ? 
                `<a href="${r.cloud_url}" target="_blank" class="text-sky-400 hover:underline flex items-center space-x-1"><i class="fa-solid fa-cloud-check text-xs"></i><span>Tersimpan di Cloud</span></a>` :
                '<span class="text-emerald-400 flex items-center space-x-1"><i class="fa-solid fa-check text-xs"></i><span>Uploaded</span></span>';
        } else if (r.cloud_status === 'uploading') {
            cloudBadge = '<span class="text-amber-400 flex items-center space-x-1"><i class="fa-solid fa-spinner fa-spin text-xs"></i><span>Sedang Upload...</span></span>';
        } else if (r.cloud_status === 'failed') {
            cloudBadge = `<span class="text-rose-400 flex items-center space-x-1 cursor-pointer" title="${r.error_message || 'Upload gagal. Klik tombol upload untuk coba lagi.'}"><i class="fa-solid fa-circle-exclamation text-xs"></i><span>Upload Gagal</span></span>`;
        }

        return `
            <tr class="hover:bg-slate-800/40 transition">
                <td class="px-4 py-3">
                    <div class="font-semibold text-white">${r.member_name}</div>
                    <div class="text-[11px] text-slate-400 truncate max-w-xs" title="${r.title}">${r.title}</div>
                </td>
                <td class="px-4 py-3 text-slate-400 whitespace-nowrap">${dateStr}</td>
                <td class="px-4 py-3 font-mono text-slate-300 whitespace-nowrap">${durStr}</td>
                <td class="px-4 py-3 font-mono text-slate-300 whitespace-nowrap">${sizeStr}</td>
                <td class="px-4 py-3">
                    <span class="px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                        r.status === 'completed' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30' :
                        r.status === 'recording' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30' :
                        'bg-slate-800 text-slate-400'
                    }">${r.status}</span>
                </td>
                <td class="px-4 py-3">${cloudBadge}</td>
                <td class="px-4 py-3 text-right whitespace-nowrap space-x-1.5">
                    ${r.file_exists ? `
                        <button onclick="playLocalVideo(${r.id}, '${encodeURIComponent(r.member_name)} - ${encodeURIComponent(r.title)}')" title="Putar Video di Browser" class="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition">
                            <i class="fa-solid fa-play"></i>
                        </button>
                        <a href="/api/recordings/${r.id}/download" title="Download File Video" class="inline-block p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition">
                            <i class="fa-solid fa-download"></i>
                        </a>
                        <button onclick="uploadToCloudManual(${r.id})" title="Upload ke Cloud Storage" class="p-1.5 text-sky-400 hover:text-sky-300 hover:bg-slate-800 rounded transition">
                            <i class="fa-solid fa-cloud-arrow-up"></i>
                        </button>
                    ` : '<span class="text-[10px] text-slate-500 italic mr-2">File dipindah/dihapus</span>'}
                    <button onclick="deleteRecording(${r.id})" title="Hapus Rekaman" class="p-1.5 text-rose-400 hover:text-rose-300 hover:bg-slate-800 rounded transition">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

async function uploadToCloudManual(id) {
    showToast('Memulai upload ke Cloud Storage...', 'info');
    try {
        const res = await fetch(`/api/recordings/${id}/upload`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast(data.message, 'success');
            loadRecordings();
        } else {
            showToast(data.error || 'Gagal memulai upload', 'error');
        }
    } catch (e) {
        showToast('Terjadi kesalahan saat memproses upload', 'error');
    }
}

async function deleteRecording(id) {
    if (!confirm('Apakah Anda yakin ingin menghapus arsip rekaman ini?')) return;
    try {
        const res = await fetch(`/api/recordings/${id}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            showToast('Rekaman berhasil dihapus.', 'success');
            loadRecordings();
            loadAppStatus();
        }
    } catch (e) {
        showToast('Gagal menghapus rekaman.', 'error');
    }
}

// --- MEMBERS WATCHLIST ---
async function loadMembers() {
    try {
        const res = await fetch('/api/members');
        const data = await res.json();
        allMembers = data.members || [];
        renderMembersGrid(allMembers);
    } catch (e) {
        console.warn('Failed to load members:', e);
    }
}

function filterMembersList() {
    const q = document.getElementById('member-search').value.toLowerCase();
    const filtered = allMembers.filter(m => 
        (m.name || '').toLowerCase().includes(q) ||
        (m.nickname || '').toLowerCase().includes(q) ||
        (m.username || '').toLowerCase().includes(q)
    );
    renderMembersGrid(filtered);
}

function renderMembersGrid(members) {
    const container = document.getElementById('members-grid');
    document.getElementById('member-count-info').textContent = `Total: ${members.length} Member`;

    if (!members || members.length === 0) {
        container.innerHTML = '<div class="col-span-full py-8 text-center text-slate-500">Tidak ada member ditemukan.</div>';
        return;
    }

    container.innerHTML = members.map(m => {
        return `
            <div class="p-3.5 rounded-xl bg-slate-900 border ${m.auto_record ? 'border-rose-900/60 bg-rose-950/10' : 'border-slate-800'} flex items-center justify-between transition">
                <div class="flex items-center space-x-3 min-w-0">
                    <div class="w-10 h-10 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-400 font-bold flex-shrink-0 overflow-hidden">
                        ${m.avatar_url ? `<img src="${m.avatar_url}" class="w-full h-full object-cover">` : m.name.charAt(0)}
                    </div>
                    <div class="min-w-0">
                        <div class="flex items-center space-x-1.5">
                            <h4 class="text-xs font-semibold text-white truncate">${m.name}</h4>
                            ${m.generation ? `<span class="text-[9px] bg-slate-800 text-slate-400 px-1 rounded">${m.generation}</span>` : ''}
                        </div>
                        <p class="text-[11px] text-slate-400 truncate">@${m.username}</p>
                    </div>
                </div>

                <div class="flex items-center space-x-2">
                    <label class="relative inline-flex items-center cursor-pointer" title="Auto Record">
                        <input type="checkbox" ${m.auto_record ? 'checked' : ''} onchange="toggleMemberAutoRecord(${m.id}, this.checked)" class="sr-only peer">
                        <div class="w-8 h-4 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-rose-600"></div>
                    </label>
                    <button onclick="deleteMember(${m.id})" title="Hapus dari Watchlist" class="text-slate-500 hover:text-rose-400 text-xs p-1">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

async function toggleMemberAutoRecord(id, status) {
    try {
        await fetch(`/api/members/${id}/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ auto_record: status })
        });
        showToast(status ? 'Auto-Record diaktifkan untuk member.' : 'Auto-Record dinonaktifkan.', 'info');
        loadMembers();
    } catch (e) {
        showToast('Gagal mengubah status auto record', 'error');
    }
}

async function toggleMasterAutoRecord(checked) {
    try {
        await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ auto_record_all_jkt48: checked ? '1' : '0' })
        });
        showToast(checked ? 'Auto-record SEMUA member JKT48 aktif!' : 'Auto-record semua dimatikan.', 'success');
        loadAppStatus();
    } catch (e) {
        showToast('Gagal mengubah pengaturan master auto-record', 'error');
    }
}

async function deleteMember(id) {
    if (!confirm('Hapus member ini dari watchlist?')) return;
    try {
        await fetch(`/api/members/${id}`, { method: 'DELETE' });
        showToast('Member dihapus dari watchlist.', 'success');
        loadMembers();
    } catch (e) {
        showToast('Gagal menghapus member', 'error');
    }
}

// --- RECORD ACTIONS ---
async function startManualRecordBySlug(slug) {
    showToast('Memulai sesi perekaman...', 'info');
    try {
        const res = await fetch('/api/record/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ slug: slug })
        });
        const data = await res.json();
        if (data.success) {
            showToast('Perekaman berhasil dimulai!', 'success');
            loadAppStatus();
            loadLiveStreams();
        } else {
            showToast(data.error || 'Gagal memulai perekaman', 'error');
        }
    } catch (e) {
        showToast('Terjadi kesalahan koneksi', 'error');
    }
}

async function stopRecordingTask(taskId) {
    if (!confirm('Hentikan proses perekaman ini?')) return;
    try {
        const res = await fetch('/api/record/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task_id: taskId })
        });
        const data = await res.json();
        if (data.success) {
            showToast('Perekaman dihentikan.', 'success');
            loadAppStatus();
            loadLiveStreams();
            loadRecordings();
        }
    } catch (e) {
        showToast('Gagal menghentikan perekaman', 'error');
    }
}

async function stopRecordingBySlug(slug) {
    // Find task_id in active recordings
    const active = (appStatus.active_recordings || []).find(s => s.slug === slug);
    if (active) {
        stopRecordingTask(active.task_id);
    }
}

// --- SETTINGS ---
async function loadSettings() {
    try {
        const res = await fetch('/api/settings');
        const data = await res.json();
        const s = data.settings || {};

        document.getElementById('setting-storage-path').value = s.storage_path || './recordings';
        document.getElementById('setting-engine').value = s.recording_engine || 'native';
        document.getElementById('setting-poll-interval').value = s.poll_interval || '20';
        
        document.getElementById('setting-cloud-provider').value = s.cloud_provider || 'none';
        document.getElementById('setting-cloud-auto-upload').checked = s.cloud_auto_upload === '1';
        document.getElementById('setting-cloud-delete-after').checked = s.cloud_delete_after_upload === '1';

        document.getElementById('setting-gdrive-folder-id').value = s.gdrive_folder_id || '';
        document.getElementById('setting-gdrive-service-json').value = s.gdrive_service_account_json || '';
        document.getElementById('setting-rclone-remote').value = s.rclone_remote_name || '';

        document.getElementById('setting-s3-endpoint').value = s.s3_endpoint_url || '';
        document.getElementById('setting-s3-bucket').value = s.s3_bucket_name || '';
        document.getElementById('setting-s3-access').value = s.s3_access_key || '';
        document.getElementById('setting-s3-secret').value = s.s3_secret_key || '';

        document.getElementById('setting-discord-webhook').value = s.discord_webhook_url || '';
        document.getElementById('setting-telegram-token').value = s.telegram_bot_token || '';
        document.getElementById('setting-telegram-chat').value = s.telegram_chat_id || '';

        onCloudProviderChange(s.cloud_provider || 'none');
    } catch (e) {
        console.warn('Failed to load settings:', e);
    }
}

function onCloudProviderChange(val) {
    document.getElementById('cloud-form-gdrive').classList.add('hidden');
    document.getElementById('cloud-form-rclone').classList.add('hidden');
    document.getElementById('cloud-form-s3').classList.add('hidden');

    if (val === 'gdrive') {
        document.getElementById('cloud-form-gdrive').classList.remove('hidden');
    } else if (val === 'rclone') {
        document.getElementById('cloud-form-rclone').classList.remove('hidden');
    } else if (val === 's3') {
        document.getElementById('cloud-form-s3').classList.remove('hidden');
    }
}

async function saveAppSettings(e) {
    e.preventDefault();
    const payload = {
        storage_path: document.getElementById('setting-storage-path').value.trim(),
        recording_engine: document.getElementById('setting-engine').value,
        poll_interval: document.getElementById('setting-poll-interval').value,
        cloud_provider: document.getElementById('setting-cloud-provider').value,
        cloud_auto_upload: document.getElementById('setting-cloud-auto-upload').checked ? '1' : '0',
        cloud_delete_after_upload: document.getElementById('setting-cloud-delete-after').checked ? '1' : '0',
        gdrive_folder_id: document.getElementById('setting-gdrive-folder-id').value.trim(),
        gdrive_service_account_json: document.getElementById('setting-gdrive-service-json').value.trim(),
        rclone_remote_name: document.getElementById('setting-rclone-remote').value.trim(),
        s3_endpoint_url: document.getElementById('setting-s3-endpoint').value.trim(),
        s3_bucket_name: document.getElementById('setting-s3-bucket').value.trim(),
        s3_access_key: document.getElementById('setting-s3-access').value.trim(),
        s3_secret_key: document.getElementById('setting-s3-secret').value.trim(),
        discord_webhook_url: document.getElementById('setting-discord-webhook').value.trim(),
        telegram_bot_token: document.getElementById('setting-telegram-token').value.trim(),
        telegram_chat_id: document.getElementById('setting-telegram-chat').value.trim()
    };

    try {
        const res = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            showToast('Semua pengaturan berhasil disimpan!', 'success');
            loadAppStatus();
        }
    } catch (e) {
        showToast('Gagal menyimpan pengaturan', 'error');
    }
}

// --- MODALS & PLAYERS ---
function previewStream(playbackUrl, encTitle, encCreator) {
    const title = decodeURIComponent(encTitle);
    const creator = decodeURIComponent(encCreator);
    
    document.getElementById('player-badge').textContent = 'PREVIEW LIVE';
    document.getElementById('player-badge').className = 'px-2 py-0.5 rounded text-[10px] font-bold bg-rose-600 text-white uppercase';
    document.getElementById('player-title').textContent = `${creator} - ${title}`;
    document.getElementById('player-info').textContent = 'Streaming langsung dari IDN App HLS';

    const video = document.getElementById('main-video-player');
    const modal = document.getElementById('player-modal');
    modal.classList.remove('hidden');

    if (Hls.isSupported()) {
        if (hlsInstance) hlsInstance.destroy();
        hlsInstance = new Hls();
        hlsInstance.loadSource(playbackUrl);
        hlsInstance.attachMedia(video);
        hlsInstance.on(Hls.Events.MANIFEST_PARSED, () => video.play());
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = playbackUrl;
        video.addEventListener('loadedmetadata', () => video.play());
    } else {
        showToast('Browser Anda tidak mendukung pemutaran HLS live stream.', 'error');
    }
}

// ================= CHAT & GIFT REPLAY =================
let currentRecordingComments = [];

async function loadRecordingComments(recordingId) {
    const container = document.getElementById('chat-list-container');
    const emptyState = document.getElementById('chat-empty-state');
    const countBadge = document.getElementById('chat-total-count');

    if (container) container.innerHTML = '<div class="text-center py-6 text-slate-500">Memuat komentar...</div>';
    if (emptyState) emptyState.classList.add('hidden');

    try {
        const res = await fetch(`/api/recordings/${recordingId}/comments`);
        const data = await res.json();
        
        if (data.success && Array.isArray(data.comments)) {
            currentRecordingComments = data.comments;
            if (countBadge) countBadge.textContent = currentRecordingComments.length;
            renderCommentsList(currentRecordingComments);
        } else {
            currentRecordingComments = [];
            if (countBadge) countBadge.textContent = '0';
            renderCommentsList([]);
        }
    } catch (e) {
        console.error('Error loading comments:', e);
        currentRecordingComments = [];
        if (countBadge) countBadge.textContent = '0';
        renderCommentsList([]);
    }
}

function renderCommentsList(comments) {
    const container = document.getElementById('chat-list-container');
    const emptyState = document.getElementById('chat-empty-state');
    if (!container) return;

    if (!comments || comments.length === 0) {
        container.innerHTML = '';
        if (emptyState) emptyState.classList.remove('hidden');
        return;
    }

    if (emptyState) emptyState.classList.add('hidden');

    container.innerHTML = comments.map(c => {
        const u = c.user || {};
        const isGift = c.type === 'gift';
        return `
            <div onclick="seekVideoTo(${c.offset_sec})" 
                 class="group flex items-start space-x-2 p-1.5 rounded-lg hover:bg-slate-900 border border-transparent hover:border-slate-800 cursor-pointer transition select-none">
                <button class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-rose-950/60 text-rose-400 border border-rose-900/50 group-hover:bg-rose-600 group-hover:text-white transition flex-shrink-0">
                    ${c.time_str || '00:00'}
                </button>
                <div class="flex-1 min-w-0">
                    <div class="flex items-center space-x-1.5">
                        <span class="font-semibold text-slate-300 truncate text-[11px]">${escapeChatHtml(u.name || u.username || 'Anon')}</span>
                        ${isGift ? '<span class="px-1 py-0.2 text-[9px] font-bold rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">GIFT</span>' : ''}
                    </div>
                    <p class="text-slate-400 text-[11px] break-words ${isGift ? 'text-amber-200 font-medium' : ''}">${escapeChatHtml(c.message || '')}</p>
                </div>
            </div>
        `;
    }).join('');
}

function filterComments(keyword) {
    const q = (keyword || '').trim().toLowerCase();
    if (!q) {
        renderCommentsList(currentRecordingComments);
        return;
    }

    const filtered = currentRecordingComments.filter(c => {
        const u = c.user || {};
        const name = (u.name || '').toLowerCase();
        const username = (u.username || '').toLowerCase();
        const msg = (c.message || '').toLowerCase();
        const time = (c.time_str || '').toLowerCase();
        return name.includes(q) || username.includes(q) || msg.includes(q) || time.includes(q);
    });

    renderCommentsList(filtered);
}

function seekVideoTo(sec) {
    const video = document.getElementById('main-video-player');
    if (video) {
        video.currentTime = Math.max(0, sec);
        video.play();
    }
}

function escapeChatHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function openLivePlayer(creator, title, playbackUrl) {
    document.getElementById('player-badge').textContent = 'PREVIEW LIVE';
    document.getElementById('player-badge').className = 'px-2 py-0.5 rounded text-[10px] font-bold bg-rose-600 text-white uppercase';
    document.getElementById('player-title').textContent = `${creator} - ${title}`;
    document.getElementById('player-info').textContent = 'Streaming langsung dari IDN App HLS';

    // Hide chat replay panel for live stream preview
    const chatPanel = document.getElementById('chat-replay-panel');
    if (chatPanel) chatPanel.classList.add('hidden');

    const video = document.getElementById('main-video-player');
    const modal = document.getElementById('player-modal');
    modal.classList.remove('hidden');

    if (Hls.isSupported()) {
        if (hlsInstance) hlsInstance.destroy();
        hlsInstance = new Hls();
        hlsInstance.loadSource(playbackUrl);
        hlsInstance.attachMedia(video);
        hlsInstance.on(Hls.Events.MANIFEST_PARSED, () => video.play());
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = playbackUrl;
        video.addEventListener('loadedmetadata', () => video.play());
    } else {
        showToast('Browser Anda tidak mendukung pemutaran HLS live stream.', 'error');
    }
}

function playLocalVideo(id, title) {
    const rec = (allRecordings || []).find(r => r.id === id);
    if (rec && rec.file_exists === false) {
        showToast('File rekaman ini sudah diunggah ke Cloud dan dihapus dari disk lokal.', 'warning');
        return;
    }

    document.getElementById('player-badge').textContent = 'ARSIP REKAMAN';
    document.getElementById('player-badge').className = 'px-2 py-0.5 rounded text-[10px] font-bold bg-sky-600 text-white uppercase';
    document.getElementById('player-title').textContent = decodeURIComponent(title);
    document.getElementById('player-info').textContent = 'Klik komentar atau menit untuk memutar pada titik tersebut';

    // Show chat replay panel
    const chatPanel = document.getElementById('chat-replay-panel');
    if (chatPanel) chatPanel.classList.remove('hidden');

    // Reset search box
    const searchInput = document.getElementById('chat-search-input');
    if (searchInput) searchInput.value = '';

    loadRecordingComments(id);

    const video = document.getElementById('main-video-player');
    const isMp4 = rec && rec.file_name && rec.file_name.toLowerCase().endsWith('.mp4');

    if (isMp4) {
        if (hlsInstance) {
            hlsInstance.destroy();
            hlsInstance = null;
        }
        video.src = `/api/recordings/${id}/stream`;
        video.play().catch(e => console.log('Autoplay deferred:', e));
    } else if (Hls.isSupported()) {
        if (hlsInstance) {
            hlsInstance.destroy();
            hlsInstance = null;
        }
        hlsInstance = new Hls({
            maxBufferSize: 300 * 1000 * 1000,
            maxBufferLength: 120,
            bufferMaxHole: 1.0,
            enableWorker: true
        });
        hlsInstance.loadSource(`/api/recordings/${id}/playlist.m3u8`);
        hlsInstance.attachMedia(video);
        hlsInstance.on(Hls.Events.MANIFEST_PARSED, () => {
            video.play().catch(e => console.log('Autoplay deferred:', e));
        });
        hlsInstance.on(Hls.Events.ERROR, (event, data) => {
            if (data.fatal) {
                console.warn('[Player] Hls fatal error, attempting stream fallback:', data);
                if (hlsInstance) {
                    hlsInstance.destroy();
                    hlsInstance = null;
                }
                video.src = `/api/recordings/${id}/stream`;
                video.play().catch(e => console.log('Autoplay deferred:', e));
            }
        });
    } else {
        video.src = `/api/recordings/${id}/stream`;
        video.play().catch(e => console.log('Autoplay deferred:', e));
    }

    document.getElementById('player-modal').classList.remove('hidden');
}

function closePlayerModal() {
    const video = document.getElementById('main-video-player');
    video.pause();
    video.src = '';
    if (hlsInstance) {
        hlsInstance.destroy();
        hlsInstance = null;
    }
    currentRecordingComments = [];
    document.getElementById('player-modal').classList.add('hidden');
}

// Manual Record Modal
function openManualRecordModal() {
    document.getElementById('manual-record-modal').classList.remove('hidden');
}

function closeManualRecordModal() {
    document.getElementById('manual-record-modal').classList.add('hidden');
}

async function submitManualRecord(e) {
    e.preventDefault();
    const payload = {
        creator_name: document.getElementById('manual-creator-name').value.trim(),
        title: document.getElementById('manual-title').value.trim(),
        playback_url: document.getElementById('manual-playback-url').value.trim()
    };

    try {
        const res = await fetch('/api/record/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            showToast('Perekaman manual berhasil dimulai!', 'success');
            closeManualRecordModal();
            loadAppStatus();
            switchTab('active');
        } else {
            showToast(data.error || 'Gagal memulai rekaman', 'error');
        }
    } catch (e) {
        showToast('Gagal menghubungi server', 'error');
    }
}

// Add Member Modal
function openAddMemberModal() {
    document.getElementById('add-member-modal').classList.remove('hidden');
}

function closeAddMemberModal() {
    document.getElementById('add-member-modal').classList.add('hidden');
}

async function submitAddMember(e) {
    e.preventDefault();
    const payload = {
        name: document.getElementById('add-mem-name').value.trim(),
        nickname: document.getElementById('add-mem-nick').value.trim(),
        username: document.getElementById('add-mem-username').value.trim(),
        generation: document.getElementById('add-mem-gen').value.trim(),
        auto_record: document.getElementById('add-mem-auto').checked
    };

    try {
        const res = await fetch('/api/members', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            showToast('Member berhasil ditambahkan ke Watchlist!', 'success');
            closeAddMemberModal();
            loadMembers();
        } else {
            showToast(data.error || 'Gagal menambahkan member', 'error');
        }
    } catch (e) {
        showToast('Gagal menghubungi server', 'error');
    }
}
