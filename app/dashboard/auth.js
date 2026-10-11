// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Edson Angelo Carara
(() => {
  const form = document.getElementById('loginForm');
  if (form) {
    form.addEventListener('submit', async event => {
      event.preventDefault(); const button = form.querySelector('button'); button.disabled = true;
      try {
        const response = await fetch('/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({username:form.username.value,password:form.password.value})});
        if (!response.ok) throw new Error(response.status===429?'Muitas tentativas. Aguarde um minuto.':'Não foi possível entrar. Confira usuário e senha.');
        form.password.value=''; window.location.replace('/');
      } catch (error) { document.getElementById('loginError').textContent=error.message; }
      finally { button.disabled=false; }
    });
    return;
  }
  window.speedtesterAuthReady = fetch('/api/auth/session').then(async response => {
    if(response.status===401){window.location.replace('/login'); return null;}
    if(!response.ok)throw new Error('Não foi possível consultar a sessão');
    const identity=await response.json(); window.speedtesterIdentity=identity;
    const operator=document.getElementById('operatorActions'), reset=document.getElementById('resetBtn');
    if(identity.role==='viewer'){operator.hidden=true;reset.hidden=true;}
    if(identity.role==='admin'){
      for(const id of ['adminToken','classifyToken']) document.getElementById(id).closest('label').hidden=true;
    }
    const status=document.getElementById('sessionStatus'); const roles={local:'Acesso local',admin:'Administrador',viewer:'Visualizador'}; status.textContent=identity.role==='local'?roles.local:identity.username+' · '+roles[identity.role];
    const logout=document.getElementById('logoutBtn'); logout.hidden=identity.role==='local';
    logout.addEventListener('click',async()=>{
      const result=await fetch('/api/auth/logout',{method:'POST',headers:{'X-CSRF-Token':identity.csrf_token||''}});
      if(result.ok)window.location.replace('/login');
    });
    return identity;
  });
})();
