import { useStore } from '../../store/AppStore';
import { Modal } from '../ui/Modal';
import { SpecEditor } from './SpecEditor';

/** Edit the working spec and capture a new version from the live dashboard. */
export function SpecEditorModal() {
  const { isSpecEditorOpen, closeSpecEditor, specName } = useStore();
  return (
    <Modal
      open={isSpecEditorOpen}
      onClose={closeSpecEditor}
      title="Edit spec"
      description={`Change specs/${specName}.yaml and capture a new version.`}
    >
      <SpecEditor />
    </Modal>
  );
}
