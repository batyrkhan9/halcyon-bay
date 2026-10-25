import { Link, Route, Routes, useLocation } from 'react-router-dom';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Shell } from './components/Shell';
import { Page } from './components/ui';
import { PeopleProvider } from './lib/people';
import AccountStory from './screens/AccountStory';
import Audit from './screens/Audit';
import Discovery from './screens/Discovery';
import JudgeBox from './screens/JudgeBox';
import Learned from './screens/Learned';
import Score from './screens/Score';
import Today from './screens/Today';
import Work from './screens/Work';

export default function App() {
  const location = useLocation();
  return (
    <PeopleProvider>
      <Shell>
        <ErrorBoundary key={location.pathname}>
        <Routes>
          <Route path="/" element={<Today />} />
          <Route path="/discovery" element={<Discovery />} />
          <Route path="/work" element={<Work />} />
          <Route path="/accounts/:id" element={<AccountStory />} />
          <Route path="/learned" element={<Learned />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/score" element={<Score />} />
          <Route path="/judge" element={<JudgeBox />} />
          <Route
            path="*"
            element={
              <Page eyebrow="Not found" title="Nothing here.">
                <Link to="/" className="text-lg font-medium text-accent hover:underline">
                  Back to today
                </Link>
              </Page>
            }
          />
        </Routes>
        </ErrorBoundary>
      </Shell>
    </PeopleProvider>
  );
}
