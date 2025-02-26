document.addEventListener('DOMContentLoaded', () => {
    console.log("Vigil ready!");
    const socket = io.connect(location.protocol + '//' + location.host + '/vigil');

    socket.on('update', (data) => {
        // Update news
        const newsContent = document.getElementById('news-content');
        newsContent.innerHTML = '';
        data.news.forEach(item => {
            const div = document.createElement('div');
            div.className = 'item';
            div.innerHTML = `
                <h3><a href="${item.url}" target="_blank">${item.title}</a></h3>
                <p>Source: ${item.source}</p>
                <a href="/save?title=${encodeURIComponent(item.title)}&url=${encodeURIComponent(item.url)}"><button>Save</button></a>
            `;
            newsContent.appendChild(div);
        });

        // Update social
        const socialContent = document.getElementById('social-content');
        socialContent.innerHTML = '';
        data.social.forEach(post => {
            const div = document.createElement('div');
            div.className = 'item';
            div.innerHTML = `<strong>${post.user}</strong>: ${post.text}`;
            socialContent.appendChild(div);
        });
    });

    // Live layout preview
    const layoutSelect = document.querySelector('select[name="layout"]');
    layoutSelect.addEventListener('change', (e) => {
        const container = document.querySelector('.container');
        container.classList.remove('grid', 'list');
        container.classList.add(e.target.value);
    });
});
