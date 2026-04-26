import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Auth0Provider } from '@auth0/auth0-react'
import './index.css'
import App from './App.tsx'

const auth0Domain = import.meta.env.VITE_AUTH0_DOMAIN
const auth0ClientId = import.meta.env.VITE_AUTH0_CLIENT_ID
const authEnabled = Boolean(auth0Domain && auth0ClientId)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {authEnabled ? (
      <Auth0Provider
        domain={auth0Domain}
        clientId={auth0ClientId}
        authorizationParams={{
          redirect_uri: window.location.origin + '/',
        }}
      >
        <App authEnabled />
      </Auth0Provider>
    ) : (
      <App authEnabled={false} />
    )}
  </StrictMode>,
)
