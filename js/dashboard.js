document.addEventListener('DOMContentLoaded', function () {
    // Check for dummy token
    if (!localStorage.getItem('adminToken')) {
        window.location.href = 'login.html';
    }

    const logoutButton = document.getElementById('logout-button');
    logoutButton.addEventListener('click', function () {
        localStorage.removeItem('adminToken');
        window.location.href = 'login.html';
    });

    const totalStudents = document.getElementById('total-students');
    const totalClasses = document.getElementById('total-classes');
    const totalQuestions = document.getElementById('total-questions');
    const totalSubjects = document.getElementById('total-subjects');
    const dailySchedule = document.getElementById('daily-schedule');

    // Fetch stats
    fetch('/admin/students')
        .then(response => response.json())
        .then(data => {
            totalStudents.textContent = data.length;
        })
        .catch(error => console.error('Error fetching students:', error));

    fetch('/admin/classes')
        .then(response => response.json())
        .then(data => {
            totalClasses.textContent = data.length;
        })
        .catch(error => console.error('Error fetching classes:', error));

    fetch('/admin/subjects')
        .then(response => response.json())
        .then(data => {
            totalSubjects.textContent = data.length;
        })
        .catch(error => console.error('Error fetching subjects:', error));
    
    // There is no /admin/questions endpoint, so we will use a placeholder
    totalQuestions.textContent = 'N/A';

    // Fetch daily schedule
    const today = new Date().toISOString().split('T')[0];
    fetch(`/admin/schedules?exam_date=${today}`)
        .then(response => response.json())
        .then(data => {
            dailySchedule.innerHTML = '';
            data.forEach(schedule => {
                const row = document.createElement('tr');
                const endTime = new Date(new Date(schedule.start_time).getTime() + schedule.duration_minutes * 60000);

                row.innerHTML = `
                    <td class="px-6 py-4 whitespace-nowrap">${schedule.subject_name}</td>
                    <td class="px-6 py-4 whitespace-nowrap">${schedule.class_id}</td>
                    <td class="px-6 py-4 whitespace-nowrap">${new Date(schedule.start_time).toLocaleTimeString()}</td>
                    <td class="px-6 py-4 whitespace-nowrap">${endTime.toLocaleTimeString()}</td>
                    <td class="px-6 py-4 whitespace-nowrap">0</td>
                `;
                dailySchedule.appendChild(row);
            });
        })
        .catch(error => console.error('Error fetching daily schedule:', error));
});
