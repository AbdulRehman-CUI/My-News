// Progressive enhancement: ordinary form submissions work without JavaScript.
const form = document.querySelector('#onboarding-form');
if (form) {
  const status = document.querySelector('#draft-status');
  let pending = Promise.resolve();
  document.querySelector('#validation-error')?.focus();
    form.addEventListener('change', () => {
      const data = new FormData(form);
      data.set('intent', 'draft');
      status.textContent = 'Saving your choices…';
      pending = pending.then(async () => {
        try {
          const response = await fetch(form.action, { method: 'POST', body: data });
          if (response.redirected) throw new Error('Your profile changed. Refresh before continuing.');
          const result = await response.json();
          if (!response.ok) throw new Error(result.error || 'Your choices could not be saved.');
          status.textContent = form.dataset.step === '7' ? 'Settings saved as a draft. Confirm them to finish setup.' : 'Your choices are saved.';
        } catch (error) {
          status.textContent = `${error.message} Use Next or Back to save and continue.`;
        }
      });
    });
    // Finish queued drafts before the navigation POST so an older draft cannot win.
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const button = event.submitter;
      form.querySelectorAll('button').forEach(item => { item.disabled = true; });
      await pending;
      if (button) {
        const intent = document.createElement('input');
        intent.type = 'hidden'; intent.name = 'intent'; intent.value = button.value;
        form.append(intent);
      }
      HTMLFormElement.prototype.submit.call(form);
    });
  const timezone = document.querySelector('#timezone');
  if (timezone?.dataset.saved === 'no') {
    const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (Array.from(timezone.options).some(option => option.value === detected)) timezone.value = detected;
  }
}
